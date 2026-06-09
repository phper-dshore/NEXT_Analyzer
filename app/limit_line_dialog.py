"""
Dialog for managing custom limit lines.
"""

import json
from typing import List, Tuple
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QInputDialog, QColorDialog, QLabel, QLineEdit, QGroupBox,
    QFormLayout, QDoubleSpinBox, QSplitter, QWidget, QAbstractItemView
)
from PyQt5.QtCore import Qt
from app.data_model import LimitLine


class LimitLineDialog(QDialog):
    """Dialog for adding, editing, and managing limit lines."""

    def __init__(self, limit_lines: List[LimitLine] = None, parent=None):
        super().__init__(parent)
        self._lines = limit_lines or []
        self._init_ui()
        self._refresh()

    def _init_ui(self):
        self.setWindowTitle("标准限值线管理")
        self.setMinimumSize(750, 500)

        main_layout = QVBoxLayout(self)

        # Line list table
        list_group = QGroupBox("限值线列表")
        list_layout = QVBoxLayout(list_group)

        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("添加限值线")
        self.add_btn.clicked.connect(self._add_line)
        self.edit_btn = QPushButton("编辑选中")
        self.edit_btn.clicked.connect(self._edit_line)
        self.remove_btn = QPushButton("删除选中")
        self.remove_btn.clicked.connect(self._remove_line)
        self.import_btn = QPushButton("导入...")
        self.import_btn.clicked.connect(self._import_lines)
        self.export_btn = QPushButton("导出...")
        self.export_btn.clicked.connect(self._export_lines)

        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.import_btn)
        btn_layout.addWidget(self.export_btn)
        list_layout.addLayout(btn_layout)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "点数", "颜色", "可见"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        list_layout.addWidget(self.table)

        main_layout.addWidget(list_group)

        # OK/Cancel
        btn_layout2 = QHBoxLayout()
        btn_layout2.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout2.addWidget(ok_btn)
        btn_layout2.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout2)

    def _refresh(self):
        self.table.setRowCount(len(self._lines))
        for i, line in enumerate(self._lines):
            name_item = QTableWidgetItem(line.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, name_item)

            points_item = QTableWidgetItem(f"{len(line.points)} 个点")
            points_item.setFlags(points_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 1, points_item)

            color_item = QTableWidgetItem(line.color)
            color_item.setFlags(color_item.flags() & ~Qt.ItemIsEditable)
            color_item.setBackground(self._get_color(line.color))
            self.table.setItem(i, 2, color_item)

            visible_item = QTableWidgetItem("是" if line.visible else "否")
            visible_item.setFlags(visible_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 3, visible_item)

    def _get_color(self, color_str):
        """Create a QColor from a string, return None if invalid."""
        from PyQt5.QtGui import QColor
        c = QColor(color_str)
        return c if c.isValid() else None

    def _add_line(self):
        dialog = _LimitLineEditDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            name, color, points = dialog.get_result()
            self._lines.append(LimitLine(name=name, color=color, points=points))
            self._refresh()

    def _edit_line(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._lines):
            QMessageBox.information(self, "提示", "请先选择一条限值线")
            return
        line = self._lines[row]
        dialog = _LimitLineEditDialog(self, line)
        if dialog.exec_() == QDialog.Accepted:
            name, color, points = dialog.get_result()
            self._lines[row] = LimitLine(
                name=name, color=color, points=points, visible=line.visible
            )
            self._refresh()

    def _remove_line(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._lines):
            QMessageBox.information(self, "提示", "请先选择一条限值线")
            return
        self._lines.pop(row)
        self._refresh()

    def _import_lines(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "导入限值线", "", "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not filepath:
            return
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            for item in data:
                name = item.get('name', '未命名')
                color = item.get('color', 'red')
                points = [(p[0], p[1]) for p in item.get('points', [])]
                self._lines.append(LimitLine(name=name, color=color, points=points))
            self._refresh()
            QMessageBox.information(self, "导入成功", f"已导入 {len(data)} 条限值线")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"导入限值线时出错:\n{str(e)}")

    def _export_lines(self):
        if not self._lines:
            QMessageBox.information(self, "提示", "没有限值线可导出")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出限值线", "limit_lines.json", "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not filepath:
            return
        try:
            data = []
            for line in self._lines:
                data.append({
                    'name': line.name,
                    'color': line.color,
                    'points': [[p[0], p[1]] for p in line.points],
                })
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "导出成功", f"已导出 {len(data)} 条限值线")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出限值线时出错:\n{str(e)}")

    def get_limit_lines(self) -> List[LimitLine]:
        return self._lines


class _LimitLineEditDialog(QDialog):
    """Dialog for editing a single limit line."""

    def __init__(self, parent=None, line: LimitLine = None):
        super().__init__(parent)
        self.setWindowTitle("编辑限值线" if line else "添加限值线")
        self.setMinimumSize(450, 350)

        layout = QVBoxLayout(self)

        # Name
        form_layout = QFormLayout()
        self.name_edit = QLineEdit(line.name if line else "")
        form_layout.addRow("名称:", self.name_edit)

        # Color
        color_layout = QHBoxLayout()
        self.color_btn = QPushButton()
        self._color = line.color if line else 'red'
        self.color_btn.setStyleSheet(f"background-color: {self._color}; min-width: 40px;")
        self.color_btn.clicked.connect(self._pick_color)
        color_layout.addWidget(self.color_btn)
        form_layout.addRow("颜色:", color_layout)
        layout.addLayout(form_layout)

        # Points table
        points_group = QGroupBox("频率-幅度点")
        points_layout = QVBoxLayout(points_group)

        btn_row = QHBoxLayout()
        self.add_point_btn = QPushButton("添加点")
        self.add_point_btn.clicked.connect(self._add_point)
        self.remove_point_btn = QPushButton("删除选中")
        self.remove_point_btn.clicked.connect(self._remove_point)
        btn_row.addWidget(self.add_point_btn)
        btn_row.addWidget(self.remove_point_btn)
        btn_row.addStretch()
        points_layout.addLayout(btn_row)

        self.points_table = QTableWidget(0, 2)
        self.points_table.setHorizontalHeaderLabels(["频率 (GHz)", "幅度 (dB)"])
        self.points_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        points_layout.addWidget(self.points_table)

        layout.addWidget(points_group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self._validate_and_accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # Load existing points (convert Hz to GHz)
        if line:
            for freq_hz, amp in line.points:
                self._add_point_row(freq_hz / 1e9, amp)

    def _pick_color(self):
        from PyQt5.QtGui import QColor
        color = QColorDialog.getColor(QColor(self._color), self)
        if color.isValid():
            self._color = color.name()
            self.color_btn.setStyleSheet(f"background-color: {self._color}; min-width: 40px;")

    def _add_point(self):
        self._add_point_row(0.01, -30)

    def _add_point_row(self, freq=0.01, amp=-30.0):
        row = self.points_table.rowCount()
        self.points_table.insertRow(row)

        freq_spin = QDoubleSpinBox()
        freq_spin.setDecimals(3)
        freq_spin.setRange(0.001, 100)
        freq_spin.setSuffix(" GHz")
        freq_spin.setValue(freq)
        self.points_table.setCellWidget(row, 0, freq_spin)

        amp_spin = QDoubleSpinBox()
        amp_spin.setDecimals(2)
        amp_spin.setRange(-200, 0)
        amp_spin.setSuffix(" dB")
        amp_spin.setValue(amp)
        self.points_table.setCellWidget(row, 1, amp_spin)

    def _remove_point(self):
        row = self.points_table.currentRow()
        if row >= 0:
            self.points_table.removeRow(row)

    def _validate_and_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入限值线名称")
            return

        if self.points_table.rowCount() < 2:
            QMessageBox.warning(self, "提示", "至少需要 2 个频率-幅度点")
            return

        self.accept()

    def get_result(self):
        name = self.name_edit.text().strip()
        points = []
        for row in range(self.points_table.rowCount()):
            freq_spin = self.points_table.cellWidget(row, 0)
            amp_spin = self.points_table.cellWidget(row, 1)
            if freq_spin and amp_spin:
                freq_ghz = freq_spin.value()
                amp_db = amp_spin.value()
                points.append((freq_ghz * 1e9, amp_db))  # Store in Hz
        # Sort by frequency
        points.sort(key=lambda x: x[0])
        return name, self._color, points
