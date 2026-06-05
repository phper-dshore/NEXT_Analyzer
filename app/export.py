"""
Export functionality for saving plots and data.
"""

import csv
import numpy as np
from typing import List, Tuple
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QWidget


def export_figure(parent: QWidget, figure, default_name: str = "next_plot"):
    """Export the current figure to an image file.

    Args:
        parent: Parent widget for the file dialog.
        figure: Matplotlib figure object.
        default_name: Default filename.
    """
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
    """Export NEXT data to CSV.

    Args:
        parent: Parent widget for the file dialog.
        frequencies: Common frequency array (Hz).
        curves: List of (column_label, data_array).
    """
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
