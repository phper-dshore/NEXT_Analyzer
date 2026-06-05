"""
Main application window for the S4P Network Analyzer tool.
Tab-based interface with VNA auto-test wizard.
"""

import os
from typing import Optional
from PyQt5.QtWidgets import (
    QMainWindow, QAction, QFileDialog, QMessageBox, QSplitter,
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QListWidget, QListWidgetItem, QApplication, QGroupBox,
    QCheckBox, QDoubleSpinBox, QFormLayout
)
import numpy as np
from PyQt5.QtCore import Qt

from app.data_model import Project, Measurement, LimitLine
from app.s4p_parser import parse_s4p
from app.import_dialog import ImportDialog
from app.plot_widget import PlotWidget
from app.pair_config_widget import PairConfigWidget
from app.limit_line_dialog import LimitLineDialog
from app.export import export_figure, export_csv, export_pdf_report
from app.test_wizard import TestWizard


class MainWindow(QMainWindow):
    """Main application window with tab-based pair navigation."""

    def __init__(self):
        super().__init__()
        self.project = Project(total_pairs=8)
        self._init_ui()
        self._update_status()

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

        self.pair_config = PairConfigWidget()
        self.pair_config.total_pairs_changed.connect(self._on_total_pairs_changed)
        self.pair_config.pair_selection_changed.connect(self._rebuild_tabs)
        left_layout.addWidget(self.pair_config)

        import_group = QGroupBox("已导入的文件")
        import_layout = QVBoxLayout(import_group)
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(120)
        import_layout.addWidget(self.file_list)

        import_btn_layout = QHBoxLayout()
        self.import_btn = QLabel('<a href="#">导入 S4P 文件...</a>')
        self.import_btn.setTextFormat(Qt.RichText)
        self.import_btn.linkActivated.connect(self._import_files)
        import_btn_layout.addWidget(self.import_btn)
        import_btn_layout.addStretch()
        import_layout.addLayout(import_btn_layout)
        left_layout.addWidget(import_group)

        # Frequency range group
        freq_group = QGroupBox("显示频率范围")
        freq_layout = QFormLayout(freq_group)

        self.freq_start_spin = QDoubleSpinBox()
        self.freq_start_spin.setDecimals(2)
        self.freq_start_spin.setRange(0.01, 100000)
        self.freq_start_spin.setValue(self.project.display_freq_start / 1e6)
        self.freq_start_spin.setSuffix(" MHz")
        self.freq_start_spin.valueChanged.connect(self._on_freq_range_changed)
        freq_layout.addRow("起始:", self.freq_start_spin)

        self.freq_stop_spin = QDoubleSpinBox()
        self.freq_stop_spin.setDecimals(1)
        self.freq_stop_spin.setRange(0.1, 100000)
        self.freq_stop_spin.setValue(self.project.display_freq_stop / 1e6)
        self.freq_stop_spin.setSuffix(" MHz")
        self.freq_stop_spin.valueChanged.connect(self._on_freq_range_changed)
        freq_layout.addRow("终止:", self.freq_stop_spin)

        self.freq_range_label = QLabel("0.10 - 500.00 MHz")
        self.freq_range_label.setStyleSheet("color: #888;")
        freq_layout.addRow("", self.freq_range_label)

        left_layout.addWidget(freq_group)

        # NEXT calculation method
        calc_group = QGroupBox("NEXT 计算方式")
        calc_layout = QVBoxLayout(calc_group)
        self.power_sum_cb = QCheckBox("功率和 (Power Sum)")
        self.power_sum_cb.setChecked(True)
        self.worst_case_cb = QCheckBox("最差值 (Worst Case)")
        self.power_sum_cb.stateChanged.connect(self._rebuild_tabs)
        self.worst_case_cb.stateChanged.connect(self._rebuild_tabs)
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

    def _get_display_freq_range(self):
        """Get display frequency range in Hz."""
        return self.freq_start_spin.value() * 1e6, self.freq_stop_spin.value() * 1e6

    def _on_freq_range_changed(self):
        """Handle frequency range changes."""
        start_mhz = self.freq_start_spin.value()
        stop_mhz = self.freq_stop_spin.value()
        self.project.display_freq_start = start_mhz * 1e6
        self.project.display_freq_stop = stop_mhz * 1e6
        self.freq_range_label.setText(f"{start_mhz:.2f} - {stop_mhz:.1f} MHz")
        self._rebuild_tabs()

    def _show_empty_tab(self):
        self.tab_widget.clear()
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.addStretch()
        label = QLabel("请在左侧导入 S4P 文件并选择要查看的线对组合\n\n"
                       "或使用「工具 → VNA 自动测试向导」自动完成测试")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 16px;")
        layout.addWidget(label)
        layout.addStretch()
        self.tab_widget.addTab(placeholder, "无数据")

    def _get_curves_for_pair(self, pa: int, pb: int):
        """Get NEXT curve data for a specific pair combination."""
        meas = self.project.get_measurement_for_pairs(pa, pb)
        if meas is None:
            return []

        curves = []
        ps_enabled = self.power_sum_cb.isChecked()
        wc_enabled = self.worst_case_cb.isChecked()

        if ps_enabled and wc_enabled:
            next_ps = self.project.compute_next(meas, 'power_sum')
            next_wc = self.project.compute_next(meas, 'worst_case')
            curves.append((f"{pa}-{pb} 功率和", meas.frequencies, next_ps))
            curves.append((f"{pa}-{pb} 最差值", meas.frequencies, next_wc))
        elif ps_enabled:
            next_ps = self.project.compute_next(meas, 'power_sum')
            curves.append((f"{pa}-{pb}", meas.frequencies, next_ps))
        elif wc_enabled:
            next_wc = self.project.compute_next(meas, 'worst_case')
            curves.append((f"{pa}-{pb}", meas.frequencies, next_wc))

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
        """Rebuild tabs with frequency range applied."""
        selected = self.pair_config.get_selected_combos()
        limit_lines = self._get_limit_line_data()
        f_start, f_stop = self._get_display_freq_range()

        self.tab_widget.clear()

        if not selected:
            self._show_empty_tab()
            return

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

    def _open_test_wizard(self):
        """Open the VNA auto-test wizard."""
        wizard = TestWizard(self)
        wizard.initialize_from_project(self.project)

        if wizard.exec_() == TestWizard.Accepted:
            # Refresh UI with new data
            self._refresh_file_list()
            loaded_combos = set()
            for m in self.project.measurements:
                loaded_combos.add(
                    (m.pair_a, m.pair_b) if m.pair_a < m.pair_b
                    else (m.pair_b, m.pair_a)
                )
            self.pair_config.set_loaded_combos(loaded_combos)

            # Update frequency range from wizard
            self.freq_start_spin.setValue(self.project.display_freq_start / 1e6)
            self.freq_stop_spin.setValue(self.project.display_freq_stop / 1e6)

            self._update_status()
            self._rebuild_tabs()

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

        pages = []
        for pa, pb in selected:
            curves = self._get_curves_for_pair(pa, pb)
            if curves:
                pages.append((f"线对 {pa}-{pb}", curves))

        if not pages:
            QMessageBox.information(self, "提示", "没有可导出的数据")
            return

        limit_lines = self._get_limit_line_data()

        # Update export module to accept frequency range
        from app.export import export_pdf_report as do_export
        f_start, f_stop = self._get_display_freq_range()
        do_export(self, pages, limit_lines, freq_range=(f_start, f_stop))

    def _export_csv(self):
        selected = self.pair_config.get_selected_combos()
        if not selected:
            QMessageBox.information(self, "提示", "没有可导出的数据")
            return

        curves = []
        reference_freq = None

        for pa, pb in selected:
            meas = self.project.get_measurement_for_pairs(pa, pb)
            if meas is None:
                continue

            ps_enabled = self.power_sum_cb.isChecked()
            wc_enabled = self.worst_case_cb.isChecked()

            if ps_enabled and wc_enabled:
                next_ps = self.project.compute_next(meas, 'power_sum')
                next_wc = self.project.compute_next(meas, 'worst_case')
                curves.append((f"线对{pa}-{pb}_功率和", next_ps))
                curves.append((f"线对{pa}-{pb}_最差值", next_wc))
            elif ps_enabled:
                next_ps = self.project.compute_next(meas, 'power_sum')
                curves.append((f"线对{pa}-{pb}", next_ps))
            elif wc_enabled:
                next_wc = self.project.compute_next(meas, 'worst_case')
                curves.append((f"线对{pa}-{pb}", next_wc))

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

        title = "高速线网分析仪 - NEXT 串音分析"
        if n_meas > 0:
            title += f" [{n_meas} 个文件, {loaded}/{expected} 线对组合]"
        self.setWindowTitle(title)

    def _show_about(self):
        QMessageBox.about(
            self, "关于",
            "高速线网分析仪 - NEXT 串音分析\n\n"
            "版本 2.1\n\n"
            "支持 Keysight VNA 自动测试\n"
            "读取 S4P 文件并分析近端串音 (NEXT) 数据\n"
            "支持自定义标准限值线对比、PDF 报告导出"
        )
