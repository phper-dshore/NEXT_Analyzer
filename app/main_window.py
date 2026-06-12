"""
Main application window for the S4P Network Analyzer tool.
Tab-based interface with VNA auto-test and persistent settings.
"""

import os
from typing import Optional
from PyQt5.QtWidgets import (
    QMainWindow, QAction, QFileDialog, QMessageBox, QSplitter,
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QListWidget, QListWidgetItem, QApplication, QGroupBox,
    QCheckBox, QDoubleSpinBox, QFormLayout, QPushButton, QComboBox,
    QLineEdit
)
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor

from app.data_model import Project, Measurement, LimitLine
from app.s4p_parser import parse_s4p
from app.import_dialog import ImportDialog
from app.plot_widget import PlotWidget
from app.pair_config_widget import PairConfigWidget
from app.limit_line_dialog import LimitLineDialog
from app.export import export_figure, export_csv, export_pdf_report
from app.test_wizard import TestWizard
from app.vna_controller import VNAController
from app import settings_manager


class MainWindow(QMainWindow):
    """Main application window with tab-based pair navigation."""

    def __init__(self):
        super().__init__()
        self.project = Project(total_pairs=8)
        self._settings = settings_manager.load_settings()
        settings_manager.settings_to_project(self._settings, self.project)
        self.vna = VNAController()
        self._init_ui()
        self._apply_settings()
        self._update_status()
        self._apply_vna_settings()
        self._update_vna_status()

    def _apply_settings(self):
        """Apply saved settings to UI controls."""
        self.pair_config.set_total_pairs(self.project.total_pairs)
        self.freq_start_spin.setValue(self.project.display_freq_start / 1e9)
        self.freq_stop_spin.setValue(self.project.display_freq_stop / 1e9)
        self.sdd21_cb.setChecked(self._settings.get("sdd21_enabled", True))
        self.power_sum_cb.setChecked(self._settings.get("power_sum_enabled", False))
        self.worst_case_cb.setChecked(self._settings.get("worst_case_enabled", False))
        self.cable_length_spin.setValue(self._settings.get("cable_length", 4.0))
        # Restore or auto-generate report number
        saved_report = self.project.report_number
        if saved_report:
            self.report_number_edit.setText(saved_report)
        else:
            self._generate_report_number()
        # Update file list
        self._refresh_file_list()
        loaded_combos = set()
        for m in self.project.measurements:
            loaded_combos.add(
                (m.pair_a, m.pair_b) if m.pair_a < m.pair_b
                else (m.pair_b, m.pair_a)
            )
        self.pair_config.set_loaded_combos(loaded_combos)

    def _save_settings(self):
        """Save current settings to file."""
        s = settings_manager.project_to_settings(self.project)
        s["visa_address"] = self._settings.get("visa_address", "")
        s["save_folder"] = self._settings.get("save_folder", "")
        s["sweep_points"] = self._settings.get("sweep_points", 1001)
        s["sdd21_enabled"] = self.sdd21_cb.isChecked()
        s["power_sum_enabled"] = self.power_sum_cb.isChecked()
        s["worst_case_enabled"] = self.worst_case_cb.isChecked()
        s["report_number"] = self.report_number_edit.text().strip()
        s["cable_length"] = self.cable_length_spin.value()
        settings_manager.save_settings(s)

    def _generate_report_number(self):
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        # Check if we have a number starting with today's date — increment or start at 001
        current = self.report_number_edit.text().strip()
        prefix = f"HTGSX{today}-"
        if current and current.startswith(prefix):
            try:
                seq = int(current.split("-")[-1])
                new_seq = seq + 1
            except (ValueError, IndexError):
                new_seq = 1
        else:
            new_seq = 1
        self.report_number_edit.setText(f"{prefix}{new_seq:03d}")
        self.project.report_number = self.report_number_edit.text()

    def closeEvent(self, event):
        """Save settings on exit."""
        self._save_settings()
        super().closeEvent(event)

    def _init_ui(self):
        self.setWindowTitle("高速线网分析仪 - NEXT 串音分析")
        self.setMinimumSize(1100, 700)

        self._create_menus()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)

        # ===== Left panel =====
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 5, 0)

        # Quick test button
        self.test_btn = QPushButton("▶ 开始自动测试")
        self.test_btn.setMinimumHeight(40)
        self.test_btn.setStyleSheet(
            "font-size: 15px; font-weight: bold; "
            "background-color: #0078d4; color: white; "
            "border-radius: 6px; padding: 6px;"
        )
        self.test_btn.clicked.connect(self._quick_test)
        left_layout.addWidget(self.test_btn)

        self.export_pdf_btn = QPushButton("导出 PDF 报告")
        self.export_pdf_btn.setMinimumHeight(36)
        self.export_pdf_btn.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "background-color: #27ae60; color: white; "
            "border-radius: 6px; padding: 6px;"
        )
        self.export_pdf_btn.clicked.connect(self._export_pdf_report)
        left_layout.addWidget(self.export_pdf_btn)

        self.save_s4p_btn = QPushButton("保存 S4P 测试报告")
        self.save_s4p_btn.setMinimumHeight(36)
        self.save_s4p_btn.setStyleSheet(
            "font-size: 14px; font-weight: bold; "
            "background-color: #d4a017; color: white; "
            "border-radius: 6px; padding: 6px;"
        )
        self.save_s4p_btn.clicked.connect(self._save_report_s4p_files)
        left_layout.addWidget(self.save_s4p_btn)

        self.pair_config = PairConfigWidget()
        self.pair_config.total_pairs_changed.connect(self._on_total_pairs_changed)
        self.pair_config.pair_selection_changed.connect(self._rebuild_tabs)
        left_layout.addWidget(self.pair_config)

        import_group = QGroupBox("已导入的文件")
        import_layout = QVBoxLayout(import_group)
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(120)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._on_file_list_context_menu)
        import_layout.addWidget(self.file_list)

        import_btn_layout = QHBoxLayout()
        self.import_btn = QLabel('<a href="#">导入 S4P 文件...</a>')
        self.import_btn.setTextFormat(Qt.RichText)
        self.import_btn.linkActivated.connect(self._import_files)
        import_btn_layout.addWidget(self.import_btn)
        import_btn_layout.addStretch()
        import_layout.addLayout(import_btn_layout)
        left_layout.addWidget(import_group)

        # Clear all data button
        self.clear_btn = QPushButton("清空数据")
        self.clear_btn.setMinimumHeight(32)
        self.clear_btn.setStyleSheet(
            "font-size: 13px; "
            "background-color: #e74c3c; color: white; "
            "border-radius: 6px; padding: 4px;"
        )
        self.clear_btn.clicked.connect(self._clear_all_data)
        left_layout.addWidget(self.clear_btn)

        # Frequency range group (GHz)
        freq_group = QGroupBox("测试/显示频率范围")
        freq_layout = QFormLayout(freq_group)

        self.freq_start_spin = QDoubleSpinBox()
        self.freq_start_spin.setDecimals(4)
        self.freq_start_spin.setRange(0.0001, 100)
        self.freq_start_spin.setValue(self.project.display_freq_start / 1e9)
        self.freq_start_spin.setSuffix(" GHz")
        self.freq_start_spin.valueChanged.connect(self._on_freq_range_changed)
        freq_layout.addRow("起始:", self.freq_start_spin)

        self.freq_stop_spin = QDoubleSpinBox()
        self.freq_stop_spin.setDecimals(4)
        self.freq_stop_spin.setRange(0.001, 100)
        self.freq_stop_spin.setValue(self.project.display_freq_stop / 1e9)
        self.freq_stop_spin.setSuffix(" GHz")
        self.freq_stop_spin.valueChanged.connect(self._on_freq_range_changed)
        freq_layout.addRow("终止:", self.freq_stop_spin)

        self.freq_range_label = QLabel("")
        self.freq_range_label.setStyleSheet("color: #888;")
        freq_layout.addRow("", self.freq_range_label)
        self._update_freq_label()

        left_layout.addWidget(freq_group)

        # Report number
        report_group = QGroupBox("测试报告编号")
        report_layout = QHBoxLayout(report_group)
        self.report_number_edit = QLineEdit()
        self.report_number_edit.setPlaceholderText("自动生成")
        report_layout.addWidget(self.report_number_edit)
        left_layout.addWidget(report_group)

        # Cable length
        cable_group = QGroupBox("测试线缆长度")
        cable_layout = QHBoxLayout(cable_group)
        cable_layout.addWidget(QLabel("长度:"))
        self.cable_length_spin = QDoubleSpinBox()
        self.cable_length_spin.setDecimals(1)
        self.cable_length_spin.setRange(0.1, 999.0)
        self.cable_length_spin.setValue(4.0)
        self.cable_length_spin.setSuffix(" M")
        self.cable_length_spin.valueChanged.connect(self._save_settings)
        cable_layout.addWidget(self.cable_length_spin)
        cable_layout.addStretch()
        left_layout.addWidget(cable_group)

        # NEXT calculation method
        calc_group = QGroupBox("NEXT 计算方式")
        calc_layout = QVBoxLayout(calc_group)
        self.sdd21_cb = QCheckBox("SDD21 (差分串音)")
        self.sdd21_cb.setChecked(True)
        self.power_sum_cb = QCheckBox("功率和 (Power Sum)")
        self.worst_case_cb = QCheckBox("最差值 (Worst Case)")
        self.sdd21_cb.stateChanged.connect(self._rebuild_tabs)
        self.power_sum_cb.stateChanged.connect(self._rebuild_tabs)
        self.worst_case_cb.stateChanged.connect(self._rebuild_tabs)
        calc_layout.addWidget(self.sdd21_cb)
        calc_layout.addWidget(self.power_sum_cb)
        calc_layout.addWidget(self.worst_case_cb)
        left_layout.addWidget(calc_group)

        left_layout.addStretch()

        # ===== Right area: Tab widget =====
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)
        self._show_empty_tab()

        splitter.addWidget(left_panel)
        splitter.addWidget(self.tab_widget)
        splitter.setSizes([300, 800])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

        self.status_label = QLabel("就绪")
        self.statusBar().addWidget(self.status_label)

        self.vna_status_label = QLabel("VNA 未连接")
        self.vna_status_label.setStyleSheet("color: #888; padding-right: 10px;")
        self.statusBar().addPermanentWidget(self.vna_status_label)

    def _create_menus(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件(&F)")

        import_action = QAction("导入 S4P 文件...", self)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self._import_files)
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        export_img_action = QAction("导出当前图片...", self)
        export_img_action.setShortcut("Ctrl+E")
        export_img_action.triggered.connect(self._export_image)
        file_menu.addAction(export_img_action)

        export_pdf_action = QAction("导出 PDF 报告（全部线对）...", self)
        export_pdf_action.setShortcut("Ctrl+R")
        export_pdf_action.triggered.connect(self._export_pdf_report)
        file_menu.addAction(export_pdf_action)

        export_csv_action = QAction("导出 CSV 数据...", self)
        export_csv_action.triggered.connect(self._export_csv)
        file_menu.addAction(export_csv_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        tools_menu = menubar.addMenu("工具(&T)")

        test_action = QAction("VNA 自动测试向导...", self)
        test_action.setShortcut("Ctrl+T")
        test_action.triggered.connect(self._open_test_wizard)
        tools_menu.addAction(test_action)

        tools_menu.addSeparator()

        limit_action = QAction("标准限值线管理...", self)
        limit_action.triggered.connect(self._manage_limit_lines)
        tools_menu.addAction(limit_action)

        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _update_freq_label(self):
        s = self.freq_start_spin.value()
        e = self.freq_stop_spin.value()
        if s >= e:
            self.freq_range_label.setText("起始频率必须小于终止频率")
            self.freq_range_label.setStyleSheet("color: red;")
        else:
            self.freq_range_label.setText(f"{s:.4f} - {e:.4f} GHz")
            self.freq_range_label.setStyleSheet("color: #888;")

    def _get_display_freq_range(self):
        """Get display frequency range in Hz."""
        start = self.freq_start_spin.value() * 1e9
        stop = self.freq_stop_spin.value() * 1e9
        if start >= stop:
            return self.project.display_freq_start, self.project.display_freq_stop
        return start, stop

    def _on_freq_range_changed(self):
        s = self.freq_start_spin.value() * 1e9
        e = self.freq_stop_spin.value() * 1e9
        self._update_freq_label()
        if s >= e:
            return
        self.project.display_freq_start = s
        self.project.display_freq_stop = e
        self._rebuild_tabs()

    def _show_empty_tab(self):
        self.tab_widget.clear()
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.addStretch()
        label = QLabel(
            "请在左侧导入 S4P 文件并选择要查看的线对组合\n\n"
            "或点击「开始自动测试」一键完成所有测试"
        )
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 16px;")
        layout.addWidget(label)
        layout.addStretch()
        self.tab_widget.addTab(placeholder, "无数据")

    def _get_curves_for_pair(self, pa: int, pb: int):
        meas = self.project.get_measurement_for_pairs(pa, pb)
        if meas is None:
            return []
        curves = []
        f_start, f_stop = self._get_display_freq_range()
        if self.sdd21_cb.isChecked():
            freq, data = self.project.compute_next_in_range(meas, f_start, f_stop, 'sdd21')
            if len(freq):
                curves.append((f"{pa}-{pb} SDD21", freq, data))
        if self.power_sum_cb.isChecked():
            freq, data = self.project.compute_next_in_range(meas, f_start, f_stop, 'power_sum')
            if len(freq):
                curves.append((f"{pa}-{pb} 功率和", freq, data))
        if self.worst_case_cb.isChecked():
            freq, data = self.project.compute_next_in_range(meas, f_start, f_stop, 'worst_case')
            if len(freq):
                curves.append((f"{pa}-{pb} 最差值", freq, data))
        return curves

    def _get_combined_curves(self, combos):
        """Collect all curves for the selected pair combinations."""
        curves = []
        for pa, pb in combos:
            curves.extend(self._get_curves_for_pair(pa, pb))
        return curves

    def _get_limit_line_data(self):
        lines = []
        for line in self.project.limit_lines:
            if not line.points:
                continue
            freqs = np.array([p[0] for p in line.points])
            values = np.array([p[1] for p in line.points])
            lines.append((line.name, freqs, values, line.color, line.visible))
        return lines

    def _rebuild_tabs(self):
        selected = self.pair_config.get_selected_combos()
        limit_lines = self._get_limit_line_data()
        f_start, f_stop = self._get_display_freq_range()
        self.tab_widget.clear()
        if not selected:
            self._show_empty_tab()
            return
        combined_curves = self._get_combined_curves(selected)
        if combined_curves:
            tab = PlotWidget(title="NEXT 合并显示")
            tab.set_curves_multi(combined_curves)
            tab.set_freq_range(f_start, f_stop)
            if limit_lines:
                tab.set_limit_lines(limit_lines)
            self.tab_widget.addTab(tab, "合并显示")
        for pa, pb in selected:
            curves = self._get_curves_for_pair(pa, pb)
            if not curves:
                continue
            tab = PlotWidget(title=f"NEXT 线对 {pa}-{pb}")
            tab.set_curves_multi(curves)
            tab.set_freq_range(f_start, f_stop)
            if limit_lines:
                tab.set_limit_lines(limit_lines)
            self.tab_widget.addTab(tab, f"线对 {pa}-{pb}")
        if self.tab_widget.count() == 0:
            self._show_empty_tab()

    def _quick_test(self):
        """Quick-start button: run configured test or prompt to configure."""
        save_folder = self._settings.get("save_folder", "")
        visa_addr = self._settings.get("visa_address", "")

        if not save_folder or not visa_addr:
            reply = QMessageBox.question(
                self, "未配置",
                "自动测试尚未配置，是否打开配置向导？\n"
                "（配置完成后，将自动开始测试）",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self._open_test_wizard()
            # Re-check after config
            save_folder = self._settings.get("save_folder", "")
            visa_addr = self._settings.get("visa_address", "")
            if not save_folder or not visa_addr:
                QMessageBox.warning(self, "配置不完整",
                    "请填写 VNA 地址和 S4P 保存路径后重试")
                return

        # Confirm the VNA is reachable before touching existing data.
        connected = self.vna.connect(visa_addr)
        if not connected:
            QMessageBox.warning(self, "连接失败",
                "无法连接到 VNA，请检查仪器状态\n"
                "或重新打开配置向导进行设置")
            self._update_vna_status()
            return

        # Confirm clearing existing measurements only after the VNA is connected.
        if self.project.measurements:
            reply = QMessageBox.question(
                self, "确认清空",
                "开始自动测试将清空当前所有已导入的测试数据。\n"
                "确定要继续吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        self.project.measurements.clear()
        self._refresh_file_list()
        self.pair_config.set_loaded_combos(set())

        # Run wizard with pre-configured settings, skip config page
        wizard = TestWizard(self, skip_config=True)
        wizard.initialize_from_project(self.project)
        wizard.set_save_folder(save_folder)
        vna_local = self._settings.get("vna_local_path", "C:\\HPData")
        if hasattr(wizard, 'vna_folder_edit'):
            wizard.vna_folder_edit.setText(vna_local)
        wizard.vna = self.vna
        # Pre-populate visa_combo so validation finds a valid address
        if hasattr(wizard, 'visa_combo'):
            wizard.visa_combo.clear()
            wizard.visa_combo.addItem(visa_addr)
            wizard.visa_combo.setCurrentIndex(0)
        # Collect config immediately to set internal fields
        wizard._collect_config()

        if wizard.exec_() == TestWizard.Accepted:
            self.project.device_model = self.vna.get_id()
            self._settings["vna_local_path"] = wizard._vna_local_path
            self._refresh_file_list()
            loaded_combos = set()
            for m in self.project.measurements:
                loaded_combos.add(
                    (m.pair_a, m.pair_b) if m.pair_a < m.pair_b
                    else (m.pair_b, m.pair_a)
                )
            self.pair_config.set_loaded_combos(loaded_combos)
            self._update_status()
            self._rebuild_tabs()
            self._generate_report_number()
        self._update_vna_status()

    def _open_test_wizard(self):
        """Open the VNA config/test wizard from the Tools menu."""
        wizard = TestWizard(self)
        wizard.initialize_from_project(self.project)
        wizard.set_save_folder(self._settings.get("save_folder", ""))
        vna_local = self._settings.get("vna_local_path", "C:\\HPData")
        if hasattr(wizard, 'vna_folder_edit'):
            wizard.vna_folder_edit.setText(vna_local)

        if wizard.exec_() == TestWizard.Accepted:
            # Always save settings (port groups, pairs, freq, etc.)
            self._settings["save_folder"] = wizard._save_folder
            self._settings["visa_address"] = wizard._visa_address
            self._settings["sweep_points"] = wizard._sweep_points
            self._settings["vna_local_path"] = wizard._vna_local_path

            # If VNA was connected, save device model
            if wizard.vna.is_connected():
                self.project.device_model = wizard.vna.get_id()

            # If measurements were added (test completed), refresh UI
            if wizard.test_results:
                self._refresh_file_list()
                loaded_combos = set()
                for m in self.project.measurements:
                    loaded_combos.add(
                        (m.pair_a, m.pair_b) if m.pair_a < m.pair_b
                        else (m.pair_b, m.pair_a)
                    )
                self.pair_config.set_loaded_combos(loaded_combos)
                self._generate_report_number()

            self.freq_start_spin.setValue(self.project.display_freq_start / 1e9)
            self.freq_stop_spin.setValue(self.project.display_freq_stop / 1e9)
            self._update_status()
            self._rebuild_tabs()
            self._save_settings()
        self._update_vna_status()

    def _import_files(self):
        total_pairs = self.pair_config.get_total_pairs()
        ports_a, ports_b = self.project.port_group_a, self.project.port_group_b
        dialog = ImportDialog(total_pairs=total_pairs, parent=self,
                              ports_a=ports_a, ports_b=ports_b)
        if dialog.exec_() == ImportDialog.Accepted:
            results = dialog.get_results()
            if not results:
                return
            imported_count = 0
            skipped_count = 0
            errors = []
            for filepath, pair_a, pair_b in results:
                # Check for duplicate pair combination
                existing = self.project.get_measurement_for_pairs(pair_a, pair_b)
                if existing:
                    QMessageBox.warning(
                        self, "线对已存在",
                        f"线对 {pair_a}-{pair_b} 已有测试数据，无法重复添加。\n"
                        f"如需替换，请先在已导入文件列表中删除该线对数据。"
                    )
                    skipped_count += 1
                    continue
                try:
                    frequencies, s_params = parse_s4p(filepath)
                    measurement = Measurement(
                        file_path=filepath,
                        pair_a=pair_a,
                        pair_b=pair_b,
                        frequencies=frequencies,
                        s_params=s_params,
                        ports_a=ports_a,
                        ports_b=ports_b,
                    )
                    self.project.add_measurement(measurement)
                    imported_count += 1
                except Exception as e:
                    errors.append(f"{os.path.basename(filepath)}: {str(e)}")

            self._refresh_file_list()
            loaded_combos = set()
            for m in self.project.measurements:
                loaded_combos.add(
                    (m.pair_a, m.pair_b) if m.pair_a < m.pair_b
                    else (m.pair_b, m.pair_a)
                )
            self.pair_config.set_loaded_combos(loaded_combos)
            self._update_status()
            self._rebuild_tabs()

            msg_parts = []
            if imported_count:
                msg_parts.append(f"成功导入 {imported_count} 个文件")
            if skipped_count:
                msg_parts.append(f"跳过 {skipped_count} 个（线对已存在）")
            if errors:
                msg_parts.append(f"失败 {len(errors)} 个")
                QMessageBox.warning(
                    self, "导入结果",
                    " | ".join(msg_parts) + "\n\n以下文件导入失败:\n" + "\n".join(errors)
                )
            elif msg_parts:
                QMessageBox.information(self, "导入完成", " | ".join(msg_parts))

    def _refresh_file_list(self):
        self.file_list.clear()
        for i, m in enumerate(self.project.measurements):
            name = f"{os.path.basename(m.file_path)} → 线对 {m.pair_a}-{m.pair_b}"
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, (m.pair_a, m.pair_b))  # store pair combo for lookup
            item.setData(Qt.UserRole + 1, i)  # store index
            self.file_list.addItem(item)

    def _delete_selected_measurement(self):
        item = self.file_list.currentItem()
        if not item:
            return
        pair_a, pair_b = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除线对 {pair_a}-{pair_b} 的测试数据吗？\n"
            f"删除后可以重新导入该线对的 S4P 文件。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Find and remove the measurement
        meas = self.project.get_measurement_for_pairs(pair_a, pair_b)
        if meas:
            self.project.measurements.remove(meas)

        self._refresh_file_list()
        loaded_combos = set()
        for m in self.project.measurements:
            loaded_combos.add(
                (m.pair_a, m.pair_b) if m.pair_a < m.pair_b
                else (m.pair_b, m.pair_a)
            )
        self.pair_config.set_loaded_combos(loaded_combos)
        self._update_status()
        self._rebuild_tabs()

    def _on_file_list_context_menu(self, pos):
        """Right-click context menu for file list."""
        item = self.file_list.itemAt(pos)
        if not item:
            return
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        delete_action = menu.addAction("删除此线对数据")
        delete_action.triggered.connect(self._delete_selected_measurement)
        menu.exec_(QCursor.pos())

    def _clear_all_data(self):
        """Clear all imported data with double confirmation."""
        if not self.project.measurements:
            QMessageBox.information(self, "提示", "没有已导入的数据")
            return
        # First confirmation
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有已导入的测试数据吗？\n"
            "此操作将删除所有 S4P 文件和线对组合数据。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        # Second confirmation
        reply = QMessageBox.question(
            self, "再次确认",
            "再次确认：清空后数据无法恢复，确定继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        # Clear all
        self.project.measurements.clear()
        self._refresh_file_list()
        loaded_combos = set()
        self.pair_config.set_loaded_combos(loaded_combos)
        self._update_status()
        self._rebuild_tabs()

    def _on_total_pairs_changed(self, n):
        self.project.total_pairs = n
        valid = []
        for m in self.project.measurements:
            if m.pair_a <= n and m.pair_b <= n:
                valid.append(m)
        self.project.measurements = valid
        self._refresh_file_list()
        loaded_combos = set()
        for m in self.project.measurements:
            loaded_combos.add(
                (m.pair_a, m.pair_b) if m.pair_a < m.pair_b
                else (m.pair_b, m.pair_a)
            )
        self.pair_config.set_loaded_combos(loaded_combos)
        self._update_status()
        self._rebuild_tabs()

    def _manage_limit_lines(self):
        dialog = LimitLineDialog(limit_lines=self.project.limit_lines, parent=self)
        if dialog.exec_() == LimitLineDialog.Accepted:
            self.project.limit_lines = dialog.get_limit_lines()
            self._rebuild_tabs()

    def _get_current_tab_plot(self):
        idx = self.tab_widget.currentIndex()
        if idx >= 0:
            w = self.tab_widget.widget(idx)
            if isinstance(w, PlotWidget):
                return w
        return None

    def _export_image(self):
        plot = self._get_current_tab_plot()
        if plot is None:
            QMessageBox.information(self, "提示", "当前标签页没有可导出的图形")
            return
        tab_text = self.tab_widget.tabText(self.tab_widget.currentIndex())
        export_figure(self, plot.get_figure(),
                      default_name=f"next_{tab_text.replace(' ', '_')}")

    def _export_pdf_report(self):
        selected = self.pair_config.get_selected_combos()
        if not selected:
            QMessageBox.information(self, "提示", "没有选中的线对组合")
            return
        per_pair_pages = []
        for pa, pb in selected:
            curves = self._get_curves_for_pair(pa, pb)
            if curves:
                per_pair_pages.append((f"线对 {pa}-{pb}", curves))
        if not per_pair_pages:
            QMessageBox.information(self, "提示", "没有可导出的数据")
            return
        combined_curves = self._get_combined_curves(selected)
        chart_pages = []
        if combined_curves:
            chart_pages.append(("合并显示", combined_curves))
        chart_pages.extend(per_pair_pages)
        limit_lines = self._get_limit_line_data()
        from app.export import export_pdf_report as do_export
        f_start, f_stop = self._get_display_freq_range()
        report_number = self.report_number_edit.text().strip()
        device_model = self.project.device_model
        cable_length = self.cable_length_spin.value()
        do_export(
            self, chart_pages, limit_lines, freq_range=(f_start, f_stop),
            tester="HAITANG", total_pairs=self.project.total_pairs,
            report_number=report_number, device_model=device_model,
            cable_length=cable_length, summary_pages=per_pair_pages
        )

    def _save_report_s4p_files(self):
        """Copy all selected S4P files to a user-chosen folder."""
        import shutil
        selected = self.pair_config.get_selected_combos()
        if not selected:
            QMessageBox.information(self, "提示", "没有选中的线对组合")
            return

        report_number = self.report_number_edit.text().strip()
        if not report_number:
            QMessageBox.warning(self, "提示", "请先生成测试报告编号")
            return

        # Let user pick the target folder
        base_dir = QFileDialog.getExistingDirectory(
            self, "选择保存文件夹（将在此目录下创建报告编号子文件夹）"
        )
        if not base_dir:
            return

        target_dir = os.path.join(base_dir, report_number)
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法创建保存目录:\n{str(e)}")
            return

        copied = 0
        errors = []
        for pa, pb in selected:
            meas = self.project.get_measurement_for_pairs(pa, pb)
            if meas is None or not os.path.exists(meas.file_path):
                errors.append(f"线对 {pa}-{pb}: 文件不存在")
                continue
            dest_name = f"pair_{pa}_{pb}.s4p"
            dest_path = os.path.join(target_dir, dest_name)
            try:
                shutil.copy2(meas.file_path, dest_path)
                copied += 1
            except Exception as e:
                errors.append(f"线对 {pa}-{pb}: {str(e)}")

        msg = f"已保存 {copied}/{len(selected)} 个 S4P 文件到:\n{target_dir}"
        if errors:
            msg += "\n\n以下文件保存失败:\n" + "\n".join(errors)
        QMessageBox.information(self, "保存完成", msg)

    def _export_csv(self):
        selected = self.pair_config.get_selected_combos()
        if not selected:
            QMessageBox.information(self, "提示", "没有可导出的数据")
            return
        curves = []
        reference_freq = None
        f_start, f_stop = self._get_display_freq_range()
        for pa, pb in selected:
            meas = self.project.get_measurement_for_pairs(pa, pb)
            if meas is None:
                continue
            measurement_freq = None
            if self.sdd21_cb.isChecked():
                freq, data = self.project.compute_next_in_range(meas, f_start, f_stop, 'sdd21')
                if len(freq):
                    measurement_freq = freq
                    curves.append((f"线对{pa}-{pb}_SDD21", data))
            if self.power_sum_cb.isChecked():
                freq, data = self.project.compute_next_in_range(meas, f_start, f_stop, 'power_sum')
                if len(freq):
                    measurement_freq = freq
                    curves.append((f"线对{pa}-{pb}_功率和", data))
            if self.worst_case_cb.isChecked():
                freq, data = self.project.compute_next_in_range(meas, f_start, f_stop, 'worst_case')
                if len(freq):
                    measurement_freq = freq
                    curves.append((f"线对{pa}-{pb}_最差值", data))
            if measurement_freq is None:
                continue
            if reference_freq is None:
                reference_freq = measurement_freq
            elif len(reference_freq) != len(measurement_freq) or not np.allclose(reference_freq, measurement_freq):
                QMessageBox.warning(
                    self, "无法导出 CSV",
                    "所选线对的频率点不一致，无法共用同一频率轴导出。\n"
                    "请只选择同一测试设置下生成的 S4P 文件，或分别导出。"
                )
                return
        if not curves:
            QMessageBox.information(self, "提示", "当前频率范围内没有可导出的数据，或未选择 NEXT 计算方式")
            return
        if reference_freq is not None:
            export_csv(self, reference_freq, curves)

    def _update_vna_status(self):
        """Update VNA connection status in the status bar."""
        if self.vna.is_connected():
            try:
                device_id = self.vna.get_id()
                short = device_id.split(',')[1] if ',' in device_id else device_id
                self.vna_status_label.setText(f"VNA 已连接: {short}")
                self.vna_status_label.setStyleSheet("color: green; font-weight: bold; padding-right: 10px;")
            except Exception:
                self.vna_status_label.setText("VNA 已连接")
                self.vna_status_label.setStyleSheet("color: green; font-weight: bold; padding-right: 10px;")
        else:
            self.vna_status_label.setText("VNA 未连接")
            self.vna_status_label.setStyleSheet("color: #888; padding-right: 10px;")

    def _apply_vna_settings(self):
        """Try to restore VNA connection from saved settings."""
        visa_addr = self._settings.get("visa_address", "")
        if visa_addr and not self.vna.is_connected():
            self.vna.connect(visa_addr)

    def _update_status(self):
        n_meas = len(self.project.measurements)
        n_pairs = self.project.total_pairs
        expected = len(self.project.get_all_expected_combinations())
        loaded = len(self.project.get_pair_combinations())
        self.status_label.setText(
            f"总对数: {n_pairs} | "
            f"已导入: {n_meas} 个 S4P 文件 | "
            f"已覆盖线对组合: {loaded}/{expected}"
        )
        title = "高速线网分析仪 - NEXT 串音分析"
        if n_meas > 0:
            title += f" [{n_meas} 个文件, {loaded}/{expected} 线对组合]"
        self.setWindowTitle(title)

    def _show_about(self):
        QMessageBox.about(
            self, "关于",
            "高速线网分析仪 - NEXT 串音分析\n\n"
            "版本 2.2\n\n"
            "支持 Keysight VNA 自动测试\n"
            "读取 S4P 文件并分析近端串音 (NEXT) 数据\n"
            "支持自定义标准限值线对比、PDF 报告导出"
        )
