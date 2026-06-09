"""
Import dialog for adding S4P files and assigning pair numbers.
Supports auto-detection of pair numbers from filenames.
"""

import os
import re
from typing import List, Optional, Tuple
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QSpinBox, QLabel, QHeaderView,
    QMessageBox, QGroupBox, QFormLayout
)
from PyQt5.QtCore import Qt


def detect_pair_from_filename(filepath: str) -> Tuple[int, int]:
    """Try to detect pair numbers from an S4P filename.

    Supported patterns:
      - pair_X_Y.s4p, pairX-Y.s4p, pair_X-Y.s4p
      - X_Y.s4p, X-Y.s4p (with at most 2 digits)
      - 线对X_Y.s4p, 线对X-Y.s4p

    Returns:
        (pair_a, pair_b) or (1, 2) if detection fails.
    """
    basename = os.path.splitext(os.path.basename(filepath))[0]
    patterns = [
        r'pair[_-]?(\d+)[_-](\d+)',
        r'线对[_-]?(\d+)[_-](\d+)',
        r'P[_-]?(\d+)[_-](\d+)',
        r'^(\d{1,2})[_-](\d{1,2})$',
    ]
    for pat in patterns:
        m = re.search(pat, basename, re.IGNORECASE)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a != b and 1 <= a <= 64 and 1 <= b <= 64:
                return (a, b)
    return (1, 2)  # fallback default


class ImportDialog(QDialog):
    """Dialog for importing S4P files and assigning pair numbers."""

    def __init__(self, total_pairs: int = 8, parent=None,
                 ports_a: Tuple[int, int] = (1, 2),
                 ports_b: Tuple[int, int] = (3, 4)):
        super().__init__(parent)
        self.total_pairs = total_pairs
        self._files = []  # List of (filepath, pair_a, pair_b)
        self._ports_a = ports_a
        self._ports_b = ports_b
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("导入 S4P 文件")
        self.setMinimumSize(750, 500)

        layout = QVBoxLayout(self)

        # Instructions
        p1, p2 = self._ports_a
        p3, p4 = self._ports_b
        layout.addWidget(QLabel(
            "添加 S4P 文件（可按住 Ctrl 一次性选择多份），文件名会自动识别线对编号：\n"
            f"VNA 端口 {p1},{p2} 连接一对线，端口 {p3},{p4} 连接另一对线。\n"
            "识别后请核对线对编号，如有重复线对请修改后再导入。"
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
        p1, p2 = self._ports_a
        p3, p4 = self._ports_b
        self.table.setHorizontalHeaderLabels(
            ["文件路径", f"线对 A (端口{p1},{p2})", f"线对 B (端口{p3},{p4})", "状态"])
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

    def _find_duplicates(self) -> set:
        """Find rows with duplicate pair combinations.

        Returns:
            Set of row indices that have duplicate (pair_a, pair_b).
        """
        seen = {}  # (a,b) → first row index
        duplicates = set()
        for i, (_, pa, pb) in enumerate(self._files):
            if pa == pb:
                duplicates.add(i)
                continue
            key = (min(pa, pb), max(pa, pb))
            if key in seen:
                duplicates.add(seen[key])
                duplicates.add(i)
            else:
                seen[key] = i
        return duplicates

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择 S4P 文件", "", "S4P 文件 (*.s4p);;Touchstone 文件 (*.s4p *.s2p *.snp);;所有文件 (*)"
        )
        for fp in files:
            if fp in [f[0] for f in self._files]:
                continue
            # Auto-detect pair numbers from filename
            pa, pb = detect_pair_from_filename(fp)
            self._files.append((fp, pa, pb))
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
        duplicates = self._find_duplicates()
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
            status, is_error = self._get_status_text(i, pa, pb, path, i in duplicates)
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            if is_error:
                status_item.setForeground(self.palette().color(self.palette().Highlight)
                                          if hasattr(self, 'palette') else None)
            self.table.setItem(i, 3, status_item)

            self.table.setCellWidget(i, 1, spin_a)
            self.table.setCellWidget(i, 2, spin_b)

    def _get_status_text(self, index: int, pa: int, pb: int, path: str,
                         is_duplicate: bool) -> Tuple[str, bool]:
        """Get status text and whether it's an error state."""
        if pa == pb:
            return "⚠ 线对编号不能相同", True
        if is_duplicate:
            return "⚠ 线对重复", True
        from_filename = detect_pair_from_filename(path)
        if from_filename != (1, 2):
            if from_filename[0] == pa and from_filename[1] == pb:
                return f"已识别 {from_filename[0]}-{from_filename[1]}", False
            else:
                return f"已修改 (原识别 {from_filename[0]}-{from_filename[1]})", False
        return "就绪", False

    def _on_pair_a_changed(self, index, value):
        if index < len(self._files):
            old_a, old_b = self._files[index][1], self._files[index][2]
            self._files[index] = (self._files[index][0], value, old_b)
            self._refresh_table()

    def _on_pair_b_changed(self, index, value):
        if index < len(self._files):
            old_a, old_b = self._files[index][1], self._files[index][2]
            self._files[index] = (self._files[index][0], old_a, value)
            self._refresh_table()

    def _update_status(self, index):
        if index < len(self._files):
            path, pa, pb = self._files[index]
            status_item = self.table.item(index, 3)
            if status_item:
                duplicates = self._find_duplicates()
                status, _ = self._get_status_text(index, pa, pb, path, index in duplicates)
                status_item.setText(status)

    def _on_accept(self):
        # Validate all files
        errors = []
        seen_pairs = {}  # normalized pair → file index
        for i, (path, pa, pb) in enumerate(self._files):
            if pa == pb:
                errors.append(f"文件 {os.path.basename(path)}: 线对 A 和 B 不能相同")
                continue
            key = (min(pa, pb), max(pa, pb))
            if key in seen_pairs:
                j = seen_pairs[key]
                errors.append(
                    f"线对 {key[0]}-{key[1]} 重复:\n"
                    f"  - 文件 {os.path.basename(self._files[j][0])}\n"
                    f"  - 文件 {os.path.basename(path)}"
                )
            else:
                seen_pairs[key] = i

        if errors:
            QMessageBox.warning(self, "导入错误", "请修正以下问题后重新导入:\n\n" + "\n".join(errors))
            return

        self.accept()

    def get_results(self) -> List[tuple]:
        """Return list of (filepath, pair_a, pair_b)."""
        return [(path, pa, pb) for path, pa, pb in self._files]

    def get_port_config(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """Return (ports_a, ports_b) for this import session."""
        return self._ports_a, self._ports_b

    def set_total_pairs(self, n: int):
        self.total_pairs = n
        self._refresh_table()
