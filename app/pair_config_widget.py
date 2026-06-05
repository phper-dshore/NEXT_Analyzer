"""
Pair configuration widget for selecting which pair combinations to display.
"""

from typing import List, Tuple, Callable, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QGroupBox,
    QScrollArea, QLabel, QPushButton, QGridLayout, QSpinBox,
    QFormLayout
)
from PyQt5.QtCore import Qt, pyqtSignal


class PairConfigWidget(QWidget):
    """Widget for configuring pair count and selecting pair combinations to view."""

    pair_selection_changed = pyqtSignal(list)  # List of (pair_a, pair_b) tuples
    total_pairs_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_pairs = 8
        self._available_combos: List[Tuple[int, int]] = []
        self._loaded_combos: set = set()  # Which combos have data loaded
        self._checkboxes: dict = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Total pairs setting
        form_layout = QFormLayout()
        self.pairs_spin = QSpinBox()
        self.pairs_spin.setMinimum(2)
        self.pairs_spin.setMaximum(64)
        self.pairs_spin.setValue(self._total_pairs)
        self.pairs_spin.valueChanged.connect(self._on_total_pairs_changed)
        form_layout.addRow("总对数:", self.pairs_spin)
        layout.addLayout(form_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.show_loaded_btn = QPushButton("仅显示已加载")
        self.show_loaded_btn.clicked.connect(self._show_only_loaded)
        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)
        btn_layout.addWidget(self.show_loaded_btn)
        layout.addLayout(btn_layout)

        # Scrollable checkbox area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.checkbox_container = QWidget()
        self.checkbox_layout = QGridLayout(self.checkbox_container)
        scroll.setWidget(self.checkbox_container)
        layout.addWidget(scroll)

        self._rebuild_checkboxes()

    def _rebuild_checkboxes(self):
        # Clear existing checkboxes
        self._checkboxes = {}
        while self.checkbox_layout.count():
            item = self.checkbox_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Create checkboxes for all pair combinations
        combos = []
        for i in range(1, self._total_pairs + 1):
            for j in range(i + 1, self._total_pairs + 1):
                combos.append((i, j))

        self._available_combos = combos

        # Arrange in a grid
        col = 0
        row = 0
        max_cols = 4

        for pa, pb in combos:
            combo_name = f"线对 {pa}-{pb}"
            cb = QCheckBox(combo_name)

            # Mark if data is loaded
            if (pa, pb) in self._loaded_combos or (pb, pa) in self._loaded_combos:
                cb.setEnabled(True)
                cb.setStyleSheet("")
            else:
                cb.setEnabled(False)
                cb.setStyleSheet("color: gray;")

            cb.stateChanged.connect(self._on_selection_changed)
            self.checkbox_layout.addWidget(cb, row, col)
            self._checkboxes[(pa, pb)] = cb

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

    def set_loaded_combos(self, combos: set):
        """Set which pair combinations have measurement data loaded."""
        self._loaded_combos = combos
        self._update_state()

    def _update_state(self):
        for (pa, pb), cb in self._checkboxes.items():
            has_data = (pa, pb) in self._loaded_combos or (pb, pa) in self._loaded_combos
            cb.setEnabled(has_data)
            if not has_data:
                cb.setChecked(False)
                cb.setStyleSheet("color: gray;")
            else:
                cb.setStyleSheet("")

    def _on_total_pairs_changed(self, value):
        self._total_pairs = value
        self._rebuild_checkboxes()
        self.total_pairs_changed.emit(value)
        self._emit_selection()

    def _select_all(self):
        for (pa, pb), cb in self._checkboxes.items():
            if cb.isEnabled():
                cb.setChecked(True)

    def _deselect_all(self):
        for cb in self._checkboxes.values():
            cb.setChecked(False)

    def _show_only_loaded(self):
        for (pa, pb), cb in self._checkboxes.items():
            cb.setChecked(cb.isEnabled())

    def _on_selection_changed(self):
        self._emit_selection()

    def _emit_selection(self):
        selected = []
        for (pa, pb), cb in self._checkboxes.items():
            if cb.isChecked():
                selected.append((pa, pb))
        self.pair_selection_changed.emit(selected)

    def get_selected_combos(self) -> List[Tuple[int, int]]:
        """Get currently selected pair combinations."""
        selected = []
        for (pa, pb), cb in self._checkboxes.items():
            if cb.isChecked():
                selected.append((pa, pb))
        return selected

    def get_total_pairs(self) -> int:
        return self._total_pairs
