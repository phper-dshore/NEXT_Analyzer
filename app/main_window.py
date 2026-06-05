"""
Main application window for the S4P Network Analyzer tool.
"""

import os
from typing import Optional
from PyQt5.QtWidgets import (
    QMainWindow, QAction, QFileDialog, QMessageBox, QSplitter,
    QWidget, QVBoxLayout, QHBoxLayout, QStatusBar, QLabel,
    QListWidget, QListWidgetItem, QApplication, QGroupBox,
    QCheckBox, QGridLayout
)
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from app.data_model import Project, Measurement, LimitLine
from app.s4p_parser import parse_s4p
from app.import_dialog import ImportDialog
from app.plot_widget import PlotWidget
from app.pair_config_widget import PairConfigWidget
from app.limit_line_dialog import LimitLineDialog
from app.export import export_figure, export_csv


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.project = Project(total_pairs=8)
        self._init_ui()
        self._update_status()
        self._update_plot()

    def _init_ui(self):
        self.setWindowTitle("高速线网分析仪 - NEXT 串音分析")
        self.setMinimumSize(1100, 700)

        # Menu bar
        self._create_menus()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        # Splitter for left panel and plot
        splitter = QSplitter(Qt.Horizontal)

        # Left panel
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 5, 0)

        # Pair configuration
        self.pair_config = PairConfigWidget()
        self.pair_config.total_pairs_changed.connect(self._on_total_pairs_changed)
        self.pair_config.pair_selection_changed.connect(self._on_selection_changed)
        left_layout.addWidget(self.pair_config)

        # Import status
        import_group = QGroupBox("已导入的文件")
        import_layout = QVBoxLayout(import_group)
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(150)
        import_layout.addWidget(self.file_list)

        import_btn_layout = QHBoxLayout()
        self.import_btn = QLabel('<a href="#">导入 S4P 文件...</a>')
        self.import_btn.setTextFormat(Qt.RichText)
        self.import_btn.linkActivated.connect(self._import_files)
        import_btn_layout.addWidget(self.import_btn)
        import_btn_layout.addStretch()
        import_layout.addLayout(import_btn_layout)

        left_layout.addWidget(import_group)

        # NEXT calculation method
        calc_group = QGroupBox("NEXT 计算方式")
        calc_layout = QVBoxLayout(calc_group)
        self.power_sum_cb = QCheckBox("功率和 (Power Sum)")
        self.power_sum_cb.setChecked(True)
        self.worst_case_cb = QCheckBox("最差值 (Worst Case)")
        self.power_sum_cb.stateChanged.connect(self._update_plot)
        self.worst_case_cb.stateChanged.connect(self._update_plot)
        calc_layout.addWidget(self.power_sum_cb)
        calc_layout.addWidget(self.worst_case_cb)
        left_layout.addWidget(calc_group)

        left_layout.addStretch()

        # Plot widget
        self.plot_widget = PlotWidget()

        # Set initial sizes for splitter (left ~300px, plot rest)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.plot_widget)
        splitter.setSizes([300, 800])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

        # Status bar
        self.status_label = QLabel("就绪")
        self.statusBar().addWidget(self.status_label)

    def _create_menus(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("文件(&F)")

        import_action = QAction("导入 S4P 文件...", self)
        import_action.setShortcut("Ctrl+I")
        import_action.triggered.connect(self._import_files)
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        export_img_action = QAction("导出图片...", self)
        export_img_action.setShortcut("Ctrl+E")
        export_img_action.triggered.connect(self._export_image)
        file_menu.addAction(export_img_action)

        export_csv_action = QAction("导出 CSV 数据...", self)
        export_csv_action.triggered.connect(self._export_csv)
        file_menu.addAction(export_csv_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Tools menu
        tools_menu = menubar.addMenu("工具(&T)")

        limit_action = QAction("标准限值线管理...", self)
        limit_action.triggered.connect(self._manage_limit_lines)
        tools_menu.addAction(limit_action)

        # Help menu
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _import_files(self):
        total_pairs = self.pair_config.get_total_pairs()
        dialog = ImportDialog(total_pairs=total_pairs, parent=self)
        if dialog.exec_() == ImportDialog.Accepted:
            results = dialog.get_results()
            if not results:
                return

            imported_count = 0
            errors = []
            for filepath, pair_a, pair_b in results:
                try:
                    frequencies, s_params = parse_s4p(filepath)
                    measurement = Measurement(
                        file_path=filepath,
                        pair_a=pair_a,
                        pair_b=pair_b,
                        frequencies=frequencies,
                        s_params=s_params,
                    )
                    self.project.add_measurement(measurement)
                    imported_count += 1
                except Exception as e:
                    errors.append(f"{os.path.basename(filepath)}: {str(e)}")

            # Refresh UI
            self._refresh_file_list()
            loaded_combos = set()
            for m in self.project.measurements:
                loaded_combos.add((m.pair_a, m.pair_b) if m.pair_a < m.pair_b else (m.pair_b, m.pair_a))
            self.pair_config.set_loaded_combos(loaded_combos)

            self._update_status()
            self._update_plot()

            # Show error summary
            if errors:
                QMessageBox.warning(
                    self, "导入警告",
                    f"成功导入 {imported_count} 个文件\n"
                    f"以下文件导入失败:\n" + "\n".join(errors)
                )

    def _refresh_file_list(self):
        self.file_list.clear()
        for m in self.project.measurements:
            name = f"{os.path.basename(m.file_path)} → 线对 {m.pair_a}-{m.pair_b}"
            item = QListWidgetItem(name)
            self.file_list.addItem(item)

    def _on_total_pairs_changed(self, n):
        self.project.total_pairs = n
        # Re-validate measurements
        valid_measurements = []
        for m in self.project.measurements:
            if m.pair_a <= n and m.pair_b <= n:
                valid_measurements.append(m)
        self.project.measurements = valid_measurements

        self._refresh_file_list()

        loaded_combos = set()
        for m in self.project.measurements:
            loaded_combos.add((m.pair_a, m.pair_b) if m.pair_a < m.pair_b else (m.pair_b, m.pair_a))
        self.pair_config.set_loaded_combos(loaded_combos)

        self._update_status()
        self._update_plot()

    def _on_selection_changed(self, selected_combos):
        self._update_plot()

    def _update_plot(self):
        selected = self.pair_config.get_selected_combos()

        # Collect curves for selected pair combinations
        curves = []
        for pa, pb in selected:
            meas = self.project.get_measurement_for_pairs(pa, pb)
            if meas is None:
                continue

            label = f"线对 {pa}-{pb}"
            label_a = min(pa, pb)
            label_b = max(pa, pb)

            if self.power_sum_cb.isChecked() and self.worst_case_cb.isChecked():
                # Show both
                next_ps = self.project.compute_next(meas, 'power_sum')
                next_wc = self.project.compute_next(meas, 'worst_case')
                freq = meas.frequencies

                # Merge frequencies if they differ across measurements
                curves.append((f"{label} (功率和)", freq, next_ps))
                curves.append((f"{label} (最差值)", freq, next_wc))
            elif self.power_sum_cb.isChecked():
                next_ps = self.project.compute_next(meas, 'power_sum')
                curves.append((label, meas.frequencies, next_ps))
            elif self.worst_case_cb.isChecked():
                next_wc = self.project.compute_next(meas, 'worst_case')
                curves.append((label, meas.frequencies, next_wc))

        self.plot_widget.set_curves(curves)

        # Add limit lines
        limit_data = []
        for line in self.project.limit_lines:
            if not line.points:
                continue
            freqs = [p[0] for p in line.points]
            values = [p[1] for p in line.points]
            limit_data.append((
                line.name,
                np.array(freqs),
                np.array(values),
                line.color,
                line.visible
            ))

        if limit_data:
            self.plot_widget.set_limit_lines(limit_data)

    def _manage_limit_lines(self):
        dialog = LimitLineDialog(limit_lines=self.project.limit_lines, parent=self)
        if dialog.exec_() == LimitLineDialog.Accepted:
            self.project.limit_lines = dialog.get_limit_lines()
            self._update_plot()

    def _export_image(self):
        export_figure(self, self.plot_widget.get_figure())

    def _export_csv(self):
        """Export displayed curve data to CSV."""
        selected = self.pair_config.get_selected_combos()
        if not selected:
            QMessageBox.information(self, "提示", "没有可导出的数据")
            return

        # Use the first measurement's frequency as reference
        curves = []
        reference_freq = None

        for pa, pb in selected:
            meas = self.project.get_measurement_for_pairs(pa, pb)
            if meas is None:
                continue

            label = f"线对 {pa}-{pb}"
            if self.power_sum_cb.isChecked() and self.worst_case_cb.isChecked():
                next_ps = self.project.compute_next(meas, 'power_sum')
                next_wc = self.project.compute_next(meas, 'worst_case')
                curves.append((f"{label}_功率和", next_ps))
                curves.append((f"{label}_最差值", next_wc))
            elif self.power_sum_cb.isChecked():
                next_ps = self.project.compute_next(meas, 'power_sum')
                curves.append((label, next_ps))
            elif self.worst_case_cb.isChecked():
                next_wc = self.project.compute_next(meas, 'worst_case')
                curves.append((label, next_wc))

            if reference_freq is None:
                reference_freq = meas.frequencies

        if reference_freq is not None:
            export_csv(self, reference_freq, curves)

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

        # Update window title
        title = "高速线网分析仪 - NEXT 串音分析"
        if n_meas > 0:
            title += f" [{n_meas} 个文件, {loaded}/{expected} 线对组合]"
        self.setWindowTitle(title)

    def _show_about(self):
        QMessageBox.about(
            self, "关于",
            "高速线网分析仪 - NEXT 串音分析\n\n"
            "版本 1.0\n\n"
            "用于读取网络分析仪 S4P 文件并分析近端串音 (NEXT) 数据。\n"
            "支持自定义标准限值线对比。"
        )
