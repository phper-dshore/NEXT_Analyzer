"""
Matplotlib-based plot widget for displaying NEXT curves.
Supports single pair-combination display with limit lines.
"""

from typing import List, Optional, Tuple
import numpy as np
import matplotlib
from matplotlib import font_manager
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QComboBox
from PyQt5.QtCore import Qt
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from app.data_model import clip_interpolated_line

# Configure CJK font for Chinese text rendering
_cjk_font_set = False
_cjk_font_candidates = [
    'Microsoft YaHei', 'SimHei',
    'PingFang SC', 'Heiti SC', 'STHeiti',
    'WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'Noto Sans CJK',
    'DejaVu Sans',
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
            matplotlib.rcParams['font.family'] = 'sans-serif'
            matplotlib.rcParams['font.sans-serif'] = [
                f for f in _cjk_font_candidates if f not in ('DejaVu Sans',)
            ] + ['DejaVu Sans']
            _cjk_font_set = True
    except Exception:
        pass


_setup_cjk_font()


class PlotWidget(QWidget):
    """Embedded matplotlib plot for a single pair combination."""

    def __init__(self, title: str = "NEXT 近端串音", parent=None):
        super().__init__(parent)
        self._title = title
        self._curve_data = {}
        self._limit_lines = []
        self._xscale = 'linear'
        self._freq_start_hz = None   # Display range: None = auto
        self._freq_stop_hz = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.axes = self.figure.add_subplot(111)

        self.toolbar = NavigationToolbar(self.canvas, self)

        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["线性频率轴", "对数频率轴"])
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.scale_combo)

        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self._setup_axes()

    def _setup_axes(self):
        self.axes.set_xlabel("频率 (GHz)")
        self.axes.set_ylabel("幅度 (dB)")
        self.axes.set_title(self._title)
        self.axes.grid(True, alpha=0.3)

    def set_title(self, title: str):
        self._title = title
        self.axes.set_title(title)

    def _on_scale_changed(self, index):
        self._xscale = 'log' if index == 1 else 'linear'
        self.refresh()

    def set_curves(self, label: str, frequencies_hz: np.ndarray, next_db: np.ndarray):
        """Set the main data curve for this plot.

        Args:
            label: Curve label (e.g. '线对 1-2 功率和')
            frequencies_hz: Frequency array in Hz
            next_db: NEXT values in dB
        """
        self._curve_data = {}
        self._curve_data[label] = {
            'freq': frequencies_hz,
            'next_db': next_db,
            'visible': True,
        }
        self.refresh()

    def set_curves_multi(self, curves: List[Tuple[str, np.ndarray, np.ndarray]]):
        """Set multiple curves (e.g. power sum + worst case) for this plot."""
        self._curve_data = {}
        for label, freq, next_db in curves:
            self._curve_data[label] = {
                'freq': freq,
                'next_db': next_db,
                'visible': True,
            }
        self.refresh()

    def set_freq_range(self, start_hz: float, stop_hz: float):
        """Set display frequency range. Data outside this range is clipped.

        Args:
            start_hz: Start frequency in Hz (None for auto).
            stop_hz: Stop frequency in Hz (None for auto).
        """
        self._freq_start_hz = start_hz
        self._freq_stop_hz = stop_hz
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
        """Redraw the plot with frequency range clipping."""
        self.axes.cla()
        self._setup_axes()

        # Determine display frequency limits
        fmin = self._freq_start_hz if self._freq_start_hz else 0
        fmax = self._freq_stop_hz if self._freq_stop_hz else float('inf')

        for label, data in self._curve_data.items():
            if not data['visible']:
                continue
            freq = data['freq']
            next_db = data['next_db']

            # Clip to frequency range
            mask = (freq >= fmin) & (freq <= fmax)
            clipped_freq = freq[mask]
            clipped_db = next_db[mask]

            if len(clipped_freq) == 0:
                continue

            freq_ghz = clipped_freq / 1e9
            self.axes.plot(freq_ghz, clipped_db, label=label, linewidth=1.5)

        for line in self._limit_lines:
            if not line['visible']:
                continue
            freq = line['freq']
            value = line['value']

            clipped_freq, clipped_val = clip_interpolated_line(
                freq, value, fmin, fmax
            )

            if len(clipped_freq) == 0:
                continue

            freq_ghz = clipped_freq / 1e9
            self.axes.plot(
                freq_ghz, clipped_val,
                label=line['name'], color=line['color'],
                linewidth=2.0, linestyle='--'
            )

        self.axes.set_xlabel("频率 (GHz)")
        self.axes.set_ylabel("幅度 (dB)")
        self.axes.set_title(self._title)
        self.axes.grid(True, alpha=0.3)

        if self._xscale == 'log':
            self.axes.set_xscale('log')
        else:
            self.axes.set_xscale('linear')

        # Set x-axis limits based on frequency range if configured
        if self._freq_start_hz is not None and self._freq_stop_hz is not None:
            self.axes.set_xlim(self._freq_start_hz / 1e9, self._freq_stop_hz / 1e9)

        handles, labels = self.axes.get_legend_handles_labels()
        if handles:
            self.axes.legend(loc='best', fontsize=8)

        self.figure.tight_layout()
        self.canvas.draw_idle()

    def save_figure(self, filepath: str):
        """Save the current figure to a file."""
        self.figure.savefig(filepath, dpi=200, bbox_inches='tight')

    def get_figure(self) -> Figure:
        return self.figure
