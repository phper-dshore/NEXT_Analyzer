"""
Export functionality for saving plots and data.
Supports single image export, CSV data export, and multi-page PDF report.
"""

import csv
import numpy as np
from typing import List, Tuple
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QWidget
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib


def _apply_plot_style(axes, title: str, xscale: str = 'linear'):
    """Apply consistent plot styling to an axes object."""
    axes.set_xlabel("频率 (MHz)")
    axes.set_ylabel("幅度 (dB)")
    axes.set_title(title)
    axes.grid(True, alpha=0.3)
    if xscale == 'log':
        axes.set_xscale('log')
    else:
        axes.set_xscale('linear')


def _build_pair_figure(
    title: str,
    curves: List[Tuple[str, np.ndarray, np.ndarray]],
    limit_lines: List[Tuple[str, np.ndarray, np.ndarray, str, bool]],
    xscale: str = 'linear',
) -> Figure:
    """Build a matplotlib Figure for a single pair combination.

    Args:
        title: Plot title.
        curves: List of (label, freq_hz, next_db).
        limit_lines: List of (name, freq_array, value_db_array, color, visible).
        xscale: 'linear' or 'log'.

    Returns:
        A matplotlib Figure ready for rendering/saving.
    """
    fig = Figure(figsize=(8.5, 5.5), dpi=150)
    ax = fig.add_subplot(111)

    for label, freq, next_db in curves:
        freq_mhz = freq / 1e6
        ax.plot(freq_mhz, next_db, label=label, linewidth=1.5)

    for name, freqs, values, color, visible in limit_lines:
        if not visible:
            continue
        freq_mhz = freqs / 1e6
        ax.plot(
            freq_mhz, values,
            label=name, color=color,
            linewidth=2.0, linestyle='--'
        )

    _apply_plot_style(ax, title, xscale)

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc='best', fontsize=8)

    fig.tight_layout()
    return fig


def export_figure(parent: QWidget, figure, default_name: str = "next_plot"):
    """Export the current figure to an image file."""
    filepath, selected_filter = QFileDialog.getSaveFileName(
        parent,
        "导出图片",
        default_name,
        "PNG (*.png);;PDF (*.pdf);;SVG (*.svg);;TIFF (*.tiff)"
    )
    if filepath:
        try:
            figure.savefig(filepath, dpi=200, bbox_inches='tight')
        except Exception as e:
            QMessageBox.critical(parent, "导出失败", f"导出图片时出错:\n{str(e)}")


def export_csv(parent: QWidget, frequencies: np.ndarray, curves: List[Tuple[str, np.ndarray]]):
    """Export NEXT data to CSV."""
    filepath, _ = QFileDialog.getSaveFileName(
        parent, "导出数据", "next_data.csv", "CSV 文件 (*.csv)"
    )
    if not filepath:
        return

    try:
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            header = ["频率 (MHz)"] + [label for label, _ in curves]
            writer.writerow(header)

            freq_mhz = frequencies / 1e6
            for i in range(len(frequencies)):
                row = [f"{freq_mhz[i]:.4f}"]
                for _, data in curves:
                    row.append(f"{data[i]:.4f}" if i < len(data) else "")
                writer.writerow(row)

        QMessageBox.information(parent, "导出成功", f"数据已保存到:\n{filepath}")
    except Exception as e:
        QMessageBox.critical(parent, "导出失败", f"导出 CSV 时出错:\n{str(e)}")


def export_pdf_report(
    parent: QWidget,
    pages: List[Tuple[str, List[Tuple[str, np.ndarray, np.ndarray]]]],
    limit_lines: List[Tuple[str, np.ndarray, np.ndarray, str, bool]],
    xscale: str = 'linear',
):
    """Export a multi-page PDF report with one chart per pair combination.

    Args:
        parent: Parent widget for file dialog.
        pages: List of (page_title, curves) where curves are
               (label, freq_hz, next_db) tuples.
        limit_lines: Limit lines to overlay on each page.
        xscale: 'linear' or 'log'.
    """
    filepath, _ = QFileDialog.getSaveFileName(
        parent, "导出 PDF 报告", "NEXT_Report.pdf",
        "PDF 文件 (*.pdf)"
    )
    if not filepath:
        return

    try:
        with PdfPages(filepath) as pdf:
            for page_title, curves in pages:
                fig = _build_pair_figure(
                    f"NEXT {page_title}", curves, limit_lines, xscale
                )
                pdf.savefig(fig)
                import matplotlib.pyplot as plt
                plt.close(fig)

        QMessageBox.information(
            parent, "导出成功",
            f"PDF 报告已保存到:\n{filepath}\n"
            f"共 {len(pages)} 页"
        )
    except Exception as e:
        QMessageBox.critical(parent, "导出失败", f"导出 PDF 时出错:\n{str(e)}")
