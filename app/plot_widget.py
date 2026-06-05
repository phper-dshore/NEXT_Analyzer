"""
Matplotlib-based plot widget for displaying NEXT curves.
"""

from typing import List, Optional, Tuple
import numpy as np
import matplotlib
from matplotlib import font_manager
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QToolBar, QAction, QComboBox
from PyQt5.QtCore import Qt
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure

# Configure CJK font for Chinese text rendering
_cjk_font_set = False
_cjk_font_candidates = [
    'Microsoft YaHei', 'SimHei',           # Windows
    'PingFang SC', 'Heiti SC', 'STHeiti',  # macOS
    'WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'Noto Sans CJK',  # Linux
    'DejaVu Sans',  # Fallback
]


def _setup_cjk_font():
    global _cjk_font_set
    if _cjk_font_set:
        return
    try:
        available = {f.name for f in font_manager.fontManager.ttflist}
        for font in _cjk_font_candidates:
            if font in available:
                matplotlib.rcParams['font.family'] = font
                _cjk_font_set = True
                break
        if not _cjk_font_set:
            # Use sans-serif family as fallback
            matplotlib.rcParams['font.family'] = 'sans-serif'
            matplotlib.rcParams['font.sans-serif'] = [f for f in _cjk_font_candidates if f not in ('DejaVu Sans',)] + ['DejaVu Sans']
            _cjk_font_set = True
    except Exception:
        pass


_setup_cjk_font()


class PlotWidget(QWidget):
    """Embedded matplotlib plot widget for NEXT frequency response."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curve_data = {}  # key -> (freq, next_db, visible)
        self._limit_lines = []  # list of (freq, value_db, name, color, visible)
        self._xscale = 'linear'  # 'linear' or 'log'
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Matplotlib figure
        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.axes = self.figure.add_subplot(111)

        # Toolbar
        self.toolbar = NavigationToolbar(self.canvas, self)

        # Scale selector
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["线性频率轴", "对数频率轴"])
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)

        # Add to toolbar
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.scale_combo)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        # Setup the plot
        self.axes.set_xlabel("频率 (MHz)")
        self.axes.set_ylabel("幅度 (dB)")
        self.axes.set_title("NEXT 近端串音")
        self.axes.grid(True, alpha=0.3)
        self.figure.tight_layout()

    def _on_scale_changed(self, index):
        self._xscale = 'log' if index == 1 else 'linear'
        self.refresh()

    def set_curves(self, curves: List[Tuple[str, np.ndarray, np.ndarray]]):
        """Set the curves to display.

        Args:
            curves: List of (label, frequencies_hz, next_db)
        """
        self._curve_data = {}
        for label, freq, next_db in curves:
            self._curve_data[label] = {
                'freq': freq,
                'next_db': next_db,
                'visible': True,
            }
        self.refresh()

    def toggle_curve(self, label: str, visible: bool):
        """Show or hide a specific curve."""
        if label in self._curve_data:
            self._curve_data[label]['visible'] = visible
            self.refresh()

    def set_limit_lines(self, lines: List[Tuple[str, np.ndarray, np.ndarray, str, bool]]):
        """Set limit lines.

        Args:
            lines: List of (name, freq_array, value_db_array, color, visible)
        """
        self._limit_lines = [
            {'name': n, 'freq': f, 'value': v, 'color': c, 'visible': vis}
            for n, f, v, c, vis in lines
        ]
        self.refresh()

    def refresh(self):
        """Redraw the plot."""
        self.axes.cla()

        # Draw curves
        for label, data in self._curve_data.items():
            if not data['visible']:
                continue
            freq_mhz = data['freq'] / 1e6
            self.axes.plot(freq_mhz, data['next_db'], label=label, linewidth=1.5)

        # Draw limit lines
        for line in self._limit_lines:
            if not line['visible']:
                continue
            freq_mhz = line['freq'] / 1e6
            self.axes.plot(
                freq_mhz, line['value'],
                label=line['name'], color=line['color'],
                linewidth=2.0, linestyle='--'
            )

        # Formatting
        self.axes.set_xlabel("频率 (MHz)")
        self.axes.set_ylabel("幅度 (dB)")
        self.axes.set_title("NEXT 近端串音")
        self.axes.grid(True, alpha=0.3)

        if self._xscale == 'log':
            self.axes.set_xscale('log')
        else:
            self.axes.set_xscale('linear')

        # Y-axis: typically negative dB values for NEXT, auto-range
        handles, labels = self.axes.get_legend_handles_labels()
        if handles:
            self.axes.legend(loc='best', fontsize=8)

        self.figure.tight_layout()
        self.canvas.draw_idle()

    def save_figure(self, filepath: str):
        """Save the current figure to a file."""
        self.figure.savefig(filepath, dpi=200, bbox_inches='tight')

    def get_figure(self) -> Figure:
        """Get the matplotlib figure for custom operations."""
        return self.figure
