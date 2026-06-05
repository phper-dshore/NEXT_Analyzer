"""
Import dialog for adding S4P files and assigning pair numbers.
"""

import os
from typing import List, Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QSpinBox, QLabel, QHeaderView,
    QMessageBox, QGroupBox, QFormLayout
)
from PyQt5.QtCore import Qt


class ImportDialog(QDialog):
    """Dialog for importing S4P files and assigning pair numbers."""

    def __init__(self, total_pairs: int = 8, parent=None):
        super().__init__(parent)
        self.total_pairs = total_pairs
        self._files = []  # List of (filepath, pair_a, pair_b)
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("导入 S4P 文件")
        self.setMinimumSize(700, 450)

        layout = QVBoxLayout(self)

        # Instructions
        layout.addWidget(QLabel(
            "添加 S4P 文件并为每个文件分配线对编号：\n"
            "端口 1-2 连接一对线，端口 3-4 连接另一对线。"
        ))

        # Button row
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("添加文件...")
        self.add_btn.clicked.connect(self._add_files)
        self.remove_btn = QPushButton("移除选中")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # File table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["文件路径", "线对 A (端口1-2)", "线对 B (端口3-4)", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        # Buttons
        self.button_layout = QHBoxLayout()
        self.ok_btn = QPushButton("确定")
        self.ok_btn.clicked.connect(self._on_accept)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.ok_btn)
        self.button_layout.addWidget(self.cancel_btn)
        layout.addLayout(self.button_layout)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择 S4P 文件", "", "S4P 文件 (*.s4p);;Touchstone 文件 (*.s4p *.s2p *.snp);;所有文件 (*)"
        )
        for fp in files:
            if fp not in [f[0] for f in self._files]:
                self._files.append((fp, 1, 2))
        self._refresh_table()

    def _remove_selected(self):
        rows = set()
        for item in self.table.selectedItems():
            rows.add(item.row())
        for row in sorted(rows, reverse=True):
            if row < len(self._files):
                self._files.pop(row)
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self._files))
        for i, (path, pa, pb) in enumerate(self._files):
            name_item = QTableWidgetItem(os.path.basename(path))
            name_item.setToolTip(path)
            self.table.setItem(i, 0, name_item)

            # Spinbox for pair A
            spin_a = QSpinBox()
            spin_a.setMinimum(1)
            spin_a.setMaximum(self.total_pairs)
            spin_a.setValue(pa)
            spin_a.valueChanged.connect(lambda v, idx=i: self._on_pair_a_changed(idx, v))
            self.table.setCellWidget(i, 1, spin_a)

            # Spinbox for pair B
            spin_b = QSpinBox()
            spin_b.setMinimum(1)
            spin_b.setMaximum(self.total_pairs)
            spin_b.setValue(pb)
            spin_b.valueChanged.connect(lambda v, idx=i: self._on_pair_b_changed(idx, v))
            self.table.setCellWidget(i, 2, spin_b)

            # Status
            status = "就绪" if pa != pb else "线对编号不能相同"
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            if pa == pb:
                status_item.setForeground(self.palette().color(self.palette().Highlight)
                                          if hasattr(self, 'palette') else None)  # Will use default red
            self.table.setItem(i, 3, status_item)

            self.table.setCellWidget(i, 1, spin_a)
            self.table.setCellWidget(i, 2, spin_b)

    def _on_pair_a_changed(self, index, value):
        if index < len(self._files):
            old_a, old_b = self._files[index][1], self._files[index][2]
            self._files[index] = (self._files[index][0], value, old_b)
            self._update_status(index)

    def _on_pair_b_changed(self, index, value):
        if index < len(self._files):
            old_a, old_b = self._files[index][1], self._files[index][2]
            self._files[index] = (self._files[index][0], old_a, value)
            self._update_status(index)

    def _update_status(self, index):
        if index < len(self._files):
            _, pa, pb = self._files[index]
            status_item = self.table.item(index, 3)
            if status_item:
                if pa == pb:
                    status_item.setText("线对编号不能相同")
                else:
                    status_item.setText("就绪")

    def _on_accept(self):
        # Validate all files
        errors = []
        for i, (path, pa, pb) in enumerate(self._files):
            if pa == pb:
                errors.append(f"文件 {os.path.basename(path)}: 线对 A 和 B 不能相同")

        if errors:
            QMessageBox.warning(self, "导入错误", "\n".join(errors))
            return

        self.accept()

    def get_results(self) -> List[tuple]:
        """Return list of (filepath, pair_a, pair_b)."""
        return [(path, pa, pb) for path, pa, pb in self._files]

    def set_total_pairs(self, n: int):
        self.total_pairs = n
        self._refresh_table()
