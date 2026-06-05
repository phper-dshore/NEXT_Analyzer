"""
Test wizard dialog for guided step-by-step VNA testing.

Walks the user through each pair combination:
1. Prompt to connect cables
2. Trigger VNA measurement
3. Wait for S4P file
4. Load and display
5. Next pair...
"""

import os
import time
import threading
from typing import List, Tuple, Optional, Callable
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFileDialog, QMessageBox, QProgressBar,
    QGroupBox, QFormLayout, QSpinBox, QDoubleSpinBox,
    QTextEdit, QWizard, QWizardPage, QComboBox,
    QGridLayout, QApplication
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject

from app.data_model import Project, Measurement
from app.s4p_parser import parse_s4p
from app.vna_controller import VNAController


class Signals(QObject):
    """Thread-safe signals for async VNA operations."""
    test_completed = pyqtSignal(int, int, bool, str)  # pair_a, pair_b, success, filepath
    progress_updated = pyqtSignal(int, int, str)  # current, total, message
    log_message = pyqtSignal(str)


class TestWizard(QWizard):
    """Guided wizard for automatic VNA testing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Optional[Project] = None
        self.vna = VNAController()
        self.signals = Signals()
        self.test_results = []  # List of (pair_a, pair_b, success, filepath)

        # Config from UI
        self._visa_address = ""
        self._save_folder = ""
        self._total_pairs = 8
        self._freq_start = 100e3
        self._freq_stop = 500e6
        self._sweep_points = 1001

        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("VNA 自动测试向导")
        self.setMinimumSize(650, 500)
        self.setWizardStyle(QWizard.ModernStyle)

        # Page 1: Configuration
        self.addPage(self._create_config_page())

        # Page 2: Testing
        self.addPage(self._create_test_page())

        # Page 3: Complete
        self.addPage(self._create_complete_page())

        self.button(QWizard.FinishButton).clicked.connect(self._on_finish)
        self.button(QWizard.CancelButton).clicked.connect(self._on_cancel)

    def _create_config_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("测试配置")
        page.setSubTitle("设置 VNA 连接和测试参数")

        layout = QVBoxLayout(page)

        # VNA connection group
        vna_group = QGroupBox("VNA 连接")
        vna_layout = QFormLayout(vna_group)

        addr_layout = QHBoxLayout()
        self.visa_combo = QComboBox()
        self.visa_combo.setEditable(True)
        self.visa_combo.setPlaceholderText("TCPIP0::192.168.1.100::inst0::INSTR")
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self._refresh_visa_resources)
        addr_layout.addWidget(self.visa_combo)
        addr_layout.addWidget(self.refresh_btn)

        vna_layout.addRow("VISA 地址:", addr_layout)

        self.connect_btn = QPushButton("连接测试")
        self.connect_btn.clicked.connect(self._test_vna_connection)
        self.connect_status = QLabel("未连接")
        connect_row = QHBoxLayout()
        connect_row.addWidget(self.connect_btn)
        connect_row.addWidget(self.connect_status)
        connect_row.addStretch()
        vna_layout.addRow("", connect_row)

        layout.addWidget(vna_group)

        # Save folder group
        folder_group = QGroupBox("S4P 保存路径")
        folder_layout = QHBoxLayout(folder_group)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("D:\\VNA_Data\\")
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(self.browse_btn)
        layout.addWidget(folder_group)

        # Test parameters group
        param_group = QGroupBox("测试参数")
        param_layout = QFormLayout(param_group)

        self.pairs_spin = QSpinBox()
        self.pairs_spin.setMinimum(2)
        self.pairs_spin.setMaximum(64)
        self.pairs_spin.setValue(8)
        param_layout.addRow("总对数:", self.pairs_spin)

        freq_layout = QHBoxLayout()
        self.freq_start_spin = QDoubleSpinBox()
        self.freq_start_spin.setDecimals(1)
        self.freq_start_spin.setRange(0.01, 100000)
        self.freq_start_spin.setValue(0.1)
        self.freq_start_spin.setSuffix(" MHz")
        self.freq_stop_spin = QDoubleSpinBox()
        self.freq_stop_spin.setDecimals(1)
        self.freq_stop_spin.setRange(0.1, 100000)
        self.freq_stop_spin.setValue(500)
        self.freq_stop_spin.setSuffix(" MHz")
        freq_layout.addWidget(QLabel("起始:"))
        freq_layout.addWidget(self.freq_start_spin)
        freq_layout.addWidget(QLabel("终止:"))
        freq_layout.addWidget(self.freq_stop_spin)
        freq_layout.addStretch()
        param_layout.addRow("频率范围:", freq_layout)

        self.points_spin = QSpinBox()
        self.points_spin.setMinimum(101)
        self.points_spin.setMaximum(10001)
        self.points_spin.setValue(1001)
        self.points_spin.setSingleStep(100)
        param_layout.addRow("扫描点数:", self.points_spin)

        layout.addWidget(param_group)
        layout.addStretch()

        return page

    def _create_test_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("自动测试")
        page.setSubTitle("按提示连接线缆并开始测试")

        layout = QVBoxLayout(page)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        # Current pair info
        self.pair_label = QLabel("准备就绪")
        self.pair_label.setAlignment(Qt.AlignCenter)
        self.pair_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        layout.addWidget(self.pair_label)

        # Instruction
        self.instruction_label = QLabel("请在左侧面板配置测试参数后开始")
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.instruction_label.setStyleSheet("font-size: 14px; color: #555; padding: 10px;")
        self.instruction_label.setWordWrap(True)
        layout.addWidget(self.instruction_label)

        # Status details
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Test button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.start_btn = QPushButton("开始测试")
        self.start_btn.setMinimumSize(150, 50)
        self.start_btn.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.start_btn.clicked.connect(self._on_start_test)
        btn_layout.addWidget(self.start_btn)

        self.skip_btn = QPushButton("跳过")
        self.skip_btn.clicked.connect(self._on_skip_test)
        btn_layout.addWidget(self.skip_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        layout.addWidget(self.log_text)

        # Connect signals
        self.signals.test_completed.connect(self._on_test_completed)
        self.signals.progress_updated.connect(self._update_progress)
        self.signals.log_message.connect(self._append_log)

        self._test_timer = None
        self._current_index = 0
        self._combinations = []

        return page

    def _create_complete_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("测试完成")
        page.setSubTitle("所有线对测试结果")

        layout = QVBoxLayout(page)

        self.summary_label = QLabel("测试完成！")
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 20px;")
        layout.addWidget(self.summary_label)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(self.result_text)

        return page

    def _refresh_visa_resources(self):
        self.visa_combo.clear()
        resources = self.vna.list_resources()
        for r in resources:
            self.visa_combo.addItem(r)
        if resources:
            self._append_log(f"找到 {len(resources)} 个 VISA 资源")

    def _test_vna_connection(self):
        address = self.visa_combo.currentText().strip()
        if address:
            self.connect_status.setText("连接中...")
            QApplication.processEvents()
            success = self.vna.connect(address)
            if success:
                self.connect_status.setText(f"已连接: {self.vna.get_id()}")
                self._append_log(f"VNA 连接成功: {self.vna.get_id()}")
            else:
                self.connect_status.setText("连接失败，使用模拟模式")
                self._append_log("VNA 连接失败，将使用模拟模式")
        else:
            QMessageBox.warning(self, "提示", "请先输入 VISA 地址")

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹")
        if folder:
            self.folder_edit.setText(folder)

    def initialize_from_project(self, project: Project):
        """Pre-fill config from project settings."""
        self.project = project
        self.pairs_spin.setValue(project.total_pairs)
        self.freq_start_spin.setValue(project.display_freq_start / 1e6)
        self.freq_stop_spin.setValue(project.display_freq_stop / 1e6)

    def _collect_config(self):
        """Read config values from UI."""
        self._visa_address = self.visa_combo.currentText().strip()
        self._save_folder = self.folder_edit.text().strip()
        self._total_pairs = self.pairs_spin.value()
        self._freq_start = int(self.freq_start_spin.value() * 1e6)
        self._freq_stop = int(self.freq_stop_spin.value() * 1e6)
        self._sweep_points = self.points_spin.value()

    def validateCurrentPage(self):
        """Validate before moving to next page."""
        if self.currentPage().title() == "测试配置":
            self._collect_config()
            if not self._save_folder:
                QMessageBox.warning(self, "提示", "请设置 S4P 保存路径")
                return False
            if not os.path.exists(self._save_folder):
                try:
                    os.makedirs(self._save_folder)
                except Exception as e:
                    QMessageBox.warning(self, "错误", f"无法创建保存路径:\n{str(e)}")
                    return False
            return True
        return super().validateCurrentPage()

    def initializePage(self, page_id: int):
        """Called when a page becomes visible."""
        if self.page(page_id).title() == "自动测试":
            self._start_test_session()

    def _start_test_session(self):
        """Begin the test session."""
        # Build combination list
        self._combinations = []
        for i in range(1, self._total_pairs + 1):
            for j in range(i + 1, self._total_pairs + 1):
                self._combinations.append((i, j))

        self._current_index = 0
        self.test_results = []
        self.progress_bar.setMaximum(len(self._combinations))

        self._show_next_pair()

    def _show_next_pair(self):
        """Show the next pair to test."""
        if self._current_index >= len(self._combinations):
            self._finish_test_session()
            return

        pa, pb = self._combinations[self._current_index]
        total = len(self._combinations)

        self.progress_bar.setValue(self._current_index)
        self.pair_label.setText(f"线对 {pa}-{pb}")
        self.instruction_label.setText(
            f"请将端口 1-2 连接到线对 {pa}，端口 3-4 连接到线对 {pb}\n"
            f"连接完成后，点击「开始测试」"
        )
        self.status_label.setText(f"进度: {self._current_index + 1} / {total}")
        self.start_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)
        self.start_btn.setText("开始测试")
        self._append_log(f"--- 线对 {pa}-{pb} ({self._current_index + 1}/{total}) ---")

    def _on_start_test(self):
        """Handle test button click."""
        if self._current_index >= len(self._combinations):
            return

        pa, pb = self._combinations[self._current_index]
        self.start_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.start_btn.setText("测试中...")
        self.instruction_label.setText("正在触发测量，请等待...")
        QApplication.processEvents()

        # Generate filename
        safe_folder = self._save_folder.replace('/', '\\')
        filename = f"pair_{pa}_{pb}.s4p"
        filepath = os.path.join(self._save_folder, filename)

        # Run measurement in background thread
        thread = threading.Thread(
            target=self._run_measurement_thread,
            args=(pa, pb, filepath),
            daemon=True
        )
        thread.start()

    def _run_measurement_thread(self, pa: int, pb: int, filepath: str):
        """Run measurement in background thread."""
        success = self.vna.take_measurement(
            save_path=filepath,
            freq_start_hz=self._freq_start,
            freq_stop_hz=self._freq_stop,
            points=self._sweep_points,
            progress_callback=lambda c, t, m:
                self.signals.progress_updated.emit(c, t, m)
        )

        if not success and self.vna.simulation_mode:
            # Wait for simulated file
            time.sleep(0.5)

        # Verify file exists
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            self.signals.test_completed.emit(pa, pb, True, filepath)
        elif self.vna.simulation_mode:
            self.signals.test_completed.emit(pa, pb, True, filepath)
        else:
            self.signals.test_completed.emit(pa, pb, False, filepath)

    def _on_test_completed(self, pa: int, pb: int, success: bool, filepath: str):
        """Handle measurement completion."""
        if success:
            self._append_log(f"线对 {pa}-{pb} 测试成功: {os.path.basename(filepath)}")
            # Parse and add to project
            try:
                frequencies, s_params = parse_s4p(filepath)
                meas = Measurement(
                    file_path=filepath,
                    pair_a=pa,
                    pair_b=pb,
                    frequencies=frequencies,
                    s_params=s_params
                )
                if self.project:
                    self.project.add_measurement(meas)
                self.test_results.append((pa, pb, True, filepath))
                self.status_label.setText(f"完成: {pa}-{pb}")
            except Exception as e:
                self._append_log(f"解析失败: {e}")
                self.test_results.append((pa, pb, False, filepath))
        else:
            self._append_log(f"线对 {pa}-{pb} 测试失败")
            self.test_results.append((pa, pb, False, filepath))

        # Move to next pair
        self._current_index += 1
        QApplication.processEvents()
        self._show_next_pair()

    def _on_skip_test(self):
        """Skip current pair."""
        if self._current_index >= len(self._combinations):
            return
        pa, pb = self._combinations[self._current_index]
        self._append_log(f"跳过线对 {pa}-{pb}")
        self.test_results.append((pa, pb, False, ""))
        self._current_index += 1
        self._show_next_pair()

    def _update_progress(self, current: int, total: int, message: str):
        """Update progress in the UI."""
        self.status_label.setText(message)
        QApplication.processEvents()

    def _append_log(self, message: str):
        """Append a log message."""
        self.log_text.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _finish_test_session(self):
        """Complete the test session."""
        self.progress_bar.setValue(len(self._combinations))
        self.pair_label.setText("全部测试完成!")
        self.instruction_label.setText("所有线对已测试完毕")
        self.start_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)

        # Build summary
        success_count = sum(1 for r in self.test_results if r[2])
        fail_count = len(self.test_results) - success_count
        self._append_log(f"\n========== 测试总结 ==========")
        self._append_log(f"总计: {len(self.test_results)} 线对")
        self._append_log(f"成功: {success_count}")
        self._append_log(f"失败: {fail_count}")

        # Update summary on complete page
        self.summary_label.setText(
            f"测试完成! 成功 {success_count}/{len(self.test_results)} 线对"
        )
        summary = f"总计测试: {len(self.test_results)} 线对\n"
        summary += f"成功: {success_count}\n"
        summary += f"失败: {fail_count}\n\n"
        for pa, pb, ok, fp in self.test_results:
            status = "✓" if ok else "✗"
            summary += f"  {status} 线对 {pa}-{pb}: "
            summary += f"{os.path.basename(fp) if fp else '跳过'}\n"
        self.result_text.setText(summary)

    def _on_finish(self):
        """Accept and pass results back."""
        # Update project settings
        if self.project:
            self.project.total_pairs = self._total_pairs
            self.project.display_freq_start = self._freq_start
            self.project.display_freq_stop = self._freq_stop
        self.accept()

    def _on_cancel(self):
        self.reject()

    def get_test_results(self):
        """Return list of (pair_a, pair_b, success, filepath)."""
        return self.test_results
