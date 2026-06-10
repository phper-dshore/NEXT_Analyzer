"""
Export functionality for saving plots and data.
Supports single image export, CSV data export, and multi-page PDF report
with cover page, PASS/FAIL summary table, and per-pair charts.
"""

import csv
import unicodedata
from datetime import datetime
from typing import List, Tuple, Optional
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QWidget
from matplotlib.figure import Figure
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import numpy as np
from app.data_model import clip_interpolated_line


def _wrap_cover_value(value: str, max_width: int = 46) -> str:
    """Wrap cover-page values using approximate rendered character widths."""
    lines = []
    current = []
    current_width = 0
    for char in str(value) or "-":
        char_width = 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        if current and current_width + char_width > max_width:
            lines.append("".join(current).rstrip())
            current = []
            current_width = 0
        current.append(char)
        current_width += char_width
    if current:
        lines.append("".join(current).rstrip())
    if len(lines) >= 2 and len(lines[-1]) < 8:
        combined = lines[-2] + lines[-1]
        split_at = combined.rfind(" ", 0, max(1, len(combined) - 8))
        if split_at > 0:
            lines[-2] = combined[:split_at].rstrip()
            lines[-1] = combined[split_at + 1:].lstrip()
    return "\n".join(lines)


def _apply_plot_style(axes, title: str, xscale: str = 'linear'):
    """Apply consistent plot styling to an axes object."""
    axes.set_xlabel("频率 (GHz)")
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
    freq_range: Optional[Tuple[float, float]] = None,
) -> Figure:
    """Build a matplotlib Figure for a single pair combination.

    Args:
        title: Plot title.
        curves: List of (label, freq_hz, next_db).
        limit_lines: List of (name, freq_array, value_db_array, color, visible).
        xscale: 'linear' or 'log'.
        freq_range: Optional (start_hz, stop_hz) for display clipping.

    Returns:
        A matplotlib Figure ready for rendering/saving.
    """
    fig = Figure(figsize=(8.5, 5.5), dpi=150)
    ax = fig.add_subplot(111)

    # Frequency clipping limits
    fmin = freq_range[0] if freq_range else 0
    fmax = freq_range[1] if freq_range else float('inf')

    for label, freq, next_db in curves:
        mask = (freq >= fmin) & (freq <= fmax)
        if not np.any(mask):
            continue
        freq_ghz = freq[mask] / 1e9
        ax.plot(freq_ghz, next_db[mask], label=label, linewidth=1.5)

    for name, freqs, values, color, visible in limit_lines:
        if not visible:
            continue
        clipped_freq, clipped_values = clip_interpolated_line(
            freqs, values, fmin, fmax
        )
        if not len(clipped_freq):
            continue
        freq_ghz = clipped_freq / 1e9
        ax.plot(
            freq_ghz, clipped_values,
            label=name, color=color,
            linewidth=2.0, linestyle='--'
        )

    _apply_plot_style(ax, title, xscale)

    # Set axis limits if frequency range is specified
    if freq_range is not None:
        ax.set_xlim(freq_range[0] / 1e9, freq_range[1] / 1e9)

    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc='best', fontsize=8)

    fig.tight_layout()
    return fig


def _add_page_number(fig, page_num: int):
    """Add page number to bottom right of a figure."""
    fig.text(0.95, 0.02, f"- {page_num} -", ha='right', va='bottom',
             fontsize=9, color='#888888')


def _create_cover_page(tester: str, date_str: str, total_pairs: int,
                       pair_count: int, limit_line_names: List[str],
                       report_number: str = "", device_model: str = "",
                       cable_length: float = 4.0) -> Figure:
    """Create a cover page for the PDF report.

    Args:
        tester: Tester name to display.
        date_str: Date string to display.
        total_pairs: Total number of cable pairs.
        pair_count: Number of pair combinations tested.
        limit_line_names: Names of limit lines used.
        report_number: Report number (e.g. "HTGSX20260608-001").
        device_model: VNA device model name.
        cable_length: Cable length in meters.

    Returns:
        A matplotlib Figure for the cover page.
    """
    fig = Figure(figsize=(8.5, 11), dpi=150)
    # All cover elements use figure coordinates so the layout cannot be
    # shifted by axes autoscaling or text content.
    fig.text(0.5, 0.88, "高速线测试分析报告", fontsize=28, fontweight='bold',
             ha='center', va='center', color='#1a1a2e')
    fig.text(0.5, 0.82, "NEXT 近端串音测试报告", fontsize=18,
             ha='center', va='center', color='#444444')

    for x1, x2, y, width in (
        (0.15, 0.85, 0.755, 2.0),
        (0.20, 0.80, 0.742, 0.5),
    ):
        fig.add_artist(Line2D(
            [x1, x2], [y, y], transform=fig.transFigure,
            color='#0078d4', linewidth=width
        ))

    cl = f"{cable_length:.1f}" if cable_length == int(cable_length) else f"{cable_length:.1f}"
    info_rows = [
        ("报告编号", report_number),
        ("测试设备", device_model),
        ("测试员", tester),
        ("测试日期", date_str),
        ("总线对数", str(total_pairs)),
        ("测试线长", f"{cl} M"),
        ("测试组合", f"{pair_count} 对"),
    ]
    if limit_line_names:
        info_rows.append(("判定标准", ', '.join(limit_line_names)))

    wrapped_rows = [
        (label, _wrap_cover_value(value))
        for label, value in info_rows
    ]
    total_text_lines = sum(value.count("\n") + 1 for _, value in wrapped_rows)
    available_height = 0.54
    line_step = min(
        0.032,
        available_height / (total_text_lines + len(wrapped_rows) * 0.65),
    )
    row_gap = line_step * 0.65
    text_linespacing = max(1.05, min(1.35, line_step / 0.024))

    y = 0.675
    for label, wrapped_value in wrapped_rows:
        line_count = wrapped_value.count("\n") + 1
        fig.text(0.15, y, f"{label}:", fontsize=13, fontweight='bold',
                 ha='left', va='top', color='#555555')
        fig.text(0.31, y, wrapped_value, fontsize=13,
                 ha='left', va='top', color='#333333',
                 linespacing=text_linespacing)
        y -= line_count * line_step + row_gap

    # Footer
    fig.text(0.5, 0.04, "— 本报告由高速线网分析仪自动生成 —",
             fontsize=10, ha='center', va='bottom', color='#888888')

    return fig


def _evaluate_pair(curves, limit_freqs, limit_values,
                   freq_range: Optional[Tuple[float, float]] = None):
    """Evaluate a pair against the limit line.

    Args:
        curves: List of (label, freq_hz, next_db) for this pair.
        limit_freqs: Limit line frequency array in Hz.
        limit_values: Limit line value array in dB.
        freq_range: Optional (start_hz, stop_hz) for evaluation clipping.

    Returns:
        (pass_bool, worst_margin, worst_freq_hz, worst_next_db, worst_label) or
        (None, None, None, None, None) if evaluation not possible.
    """
    if not curves or len(limit_freqs) < 2:
        return None, None, None, None, None

    order = np.argsort(limit_freqs)
    limit_freqs = np.asarray(limit_freqs)[order]
    limit_values = np.asarray(limit_values)[order]
    eval_min = max(freq_range[0], limit_freqs[0]) if freq_range else limit_freqs[0]
    eval_max = min(freq_range[1], limit_freqs[-1]) if freq_range else limit_freqs[-1]
    if eval_min > eval_max:
        return None, None, None, None, None

    overall_pass = True
    overall_worst_margin = float('inf')
    overall_worst_freq = 0
    overall_worst_next = 0
    overall_worst_label = ""

    for label, freq, next_db in curves:
        mask = (freq >= eval_min) & (freq <= eval_max)
        if not np.any(mask):
            continue
        freq = freq[mask]
        next_db = next_db[mask]
        # Interpolate limit at measurement frequencies
        limit_interp = np.interp(freq, limit_freqs, limit_values)
        # Margin = limit - NEXT (positive = pass, negative = fail)
        margin = limit_interp - next_db
        min_margin = np.min(margin)
        min_idx = np.argmin(margin)

        if min_margin < overall_worst_margin:
            overall_worst_margin = min_margin
            overall_worst_freq = freq[min_idx]
            overall_worst_next = next_db[min_idx]
            overall_worst_label = label

        if min_margin < 0:
            overall_pass = False

    if overall_worst_margin == float('inf'):
        return None, None, None, None, None

    return overall_pass, overall_worst_margin, overall_worst_freq, overall_worst_next, overall_worst_label


def _create_summary_page(pages, limit_lines, tester,
                         freq_range: Optional[Tuple[float, float]] = None,
                         summary_page_index: int = 1,
                         summary_page_count: int = 1) -> Figure:
    """Create a summary table page with PASS/FAIL results.

    Args:
        pages: List of (page_title, curves) pairs.
        limit_lines: List of visible limit lines for evaluation.
        tester: Tester name.
        freq_range: Optional (start_hz, stop_hz) for evaluation clipping.
        summary_page_index: Current summary-page number.
        summary_page_count: Total number of summary pages.

    Returns:
        A matplotlib Figure with the summary table.
    """
    fig = Figure(figsize=(8.5, 11), dpi=150)
    ax = fig.add_subplot(111)
    ax.axis('off')

    # Title
    title = "综合测试结果"
    if summary_page_count > 1:
        title += f" ({summary_page_index}/{summary_page_count})"
    ax.text(0.5, 0.96, title, fontsize=20, fontweight='bold',
            ha='center', va='center', color='#1a1a2e')

    # Find the first visible limit line for evaluation
    limit_freqs = None
    limit_values = None
    limit_name = ""
    for name, lf, lv, color, visible in limit_lines:
        if visible and len(lf) >= 2:
            limit_freqs = lf
            limit_values = lv
            limit_name = name
            break

    # Build table data
    col_labels = ["线对组合", "结果", "最差频率", "最差点(dB)", "余量(dB)"]
    rows = []
    for page_title, curves in pages:
        pair_name = page_title.replace("线对 ", "")
        if limit_freqs is not None:
            passed, worst_margin, worst_freq, worst_next, worst_label = _evaluate_pair(
                curves, limit_freqs, limit_values, freq_range)
            if passed is None:
                result = "—"
                worst_freq_str = "—"
                worst_point_str = "—"
                margin_str = "—"
            else:
                result = "PASS" if passed else "FAIL"
                worst_freq_str = f"{worst_freq / 1e9:.3f} GHz"
                worst_point_str = f"{worst_next:.1f}"
                margin_str = f"{worst_margin:+.1f}"
        else:
            result = "—"
            worst_freq_str = "—"
            worst_point_str = "—"
            margin_str = "—"
        rows.append((pair_name, result, worst_freq_str, worst_point_str, margin_str))

    # Draw table
    n_rows = len(rows) + 1  # +1 for header
    n_cols = len(col_labels)

    # Calculate table dimensions
    table_top = 0.90
    row_height = min(0.035, 0.75 / n_rows)

    # Draw header
    header_y = table_top
    for j, label in enumerate(col_labels):
        x = 0.05 + j * 0.18
        ax.text(x + 0.09, header_y, label, fontsize=10, fontweight='bold',
                ha='center', va='center', color='white',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#0078d4', edgecolor='none'))

    # Draw rows
    for i, row in enumerate(rows):
        y = header_y - (i + 1) * row_height
        for j, val in enumerate(row):
            x = 0.05 + j * 0.18
            color = '#333333'
            bg = '#f8f8f8' if i % 2 == 0 else 'white'

            if j == 1:  # Result column
                if val == "PASS":
                    color = '#27ae60'
                    bg = '#e8f8f0'
                elif val == "FAIL":
                    color = '#e74c3c'
                    bg = '#fde8e8'

            ax.text(x + 0.09, y, val, fontsize=9, ha='center', va='center',
                    color=color,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor=bg, edgecolor='#dddddd', linewidth=0.5))

    # Footer info
    footer_info = f"测试员: {tester}"
    if limit_name:
        footer_info += f"    判定标准: {limit_name}"
    ax.text(0.5, 0.02, footer_info, fontsize=9, ha='center', va='center', color='#888888')

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
            header = ["频率 (GHz)"] + [label for label, _ in curves]
            writer.writerow(header)

            freq_ghz = frequencies / 1e9
            for i in range(len(frequencies)):
                row = [f"{freq_ghz[i]:.6f}"]
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
    freq_range: Optional[Tuple[float, float]] = None,
    tester: str = "HAITANG",
    total_pairs: int = 8,
    report_number: str = "",
    device_model: str = "",
    cable_length: float = 4.0,
):
    """Export a multi-page PDF report with cover, summary, and per-pair charts.

    Args:
        parent: Parent widget for file dialog.
        pages: List of (page_title, curves) where curves are
               (label, freq_hz, next_db) tuples.
        limit_lines: Limit lines to overlay on each page.
        xscale: 'linear' or 'log'.
        freq_range: Optional (start_hz, stop_hz) for display clipping.
        tester: Tester name for the report cover.
        total_pairs: Total number of cable pairs.
        report_number: Report number (e.g. "HTGSX20260608-001").
        device_model: VNA device model name.
        cable_length: Cable length in meters.
    """
    default_name = f"{report_number}.pdf" if report_number else "NEXT_Report.pdf"
    filepath, _ = QFileDialog.getSaveFileName(
        parent, "导出 PDF 报告", default_name,
        "PDF 文件 (*.pdf)"
    )
    if not filepath:
        return

    try:
        date_str = datetime.now().strftime("%Y年%m月%d日")
        limit_names = [n for n, _, _, _, v in limit_lines if v and len(n) > 0]

        with PdfPages(filepath) as pdf:
            # Page counter (starts after cover)
            page_num = 1

            # 1. Cover page (no page number)
            cover = _create_cover_page(
                tester, date_str, total_pairs, len(pages), limit_names,
                report_number, device_model, cable_length
            )
            pdf.savefig(cover)
            plt.close(cover)

            # 2. Summary pages. Keep row height readable for large pair counts.
            rows_per_summary_page = 28
            summary_chunks = [
                pages[i:i + rows_per_summary_page]
                for i in range(0, len(pages), rows_per_summary_page)
            ] or [[]]
            for index, chunk in enumerate(summary_chunks, start=1):
                summary = _create_summary_page(
                    chunk, limit_lines, tester, freq_range,
                    summary_page_index=index,
                    summary_page_count=len(summary_chunks),
                )
                _add_page_number(summary, page_num)
                page_num += 1
                pdf.savefig(summary)
                plt.close(summary)

            # 3. Per-pair chart pages
            for page_title, curves in pages:
                fig = _build_pair_figure(
                    f"NEXT {page_title}", curves, limit_lines,
                    xscale, freq_range
                )
                _add_page_number(fig, page_num)
                page_num += 1
                pdf.savefig(fig)
                plt.close(fig)

        QMessageBox.information(
            parent, "导出成功",
            f"PDF 报告已保存到:\n{filepath}\n"
            f"共 {len(pages) + len(summary_chunks) + 1} 页"
            f"（封面 + {len(summary_chunks)} 页汇总 + {len(pages)} 线对图表）"
        )
    except Exception as e:
        QMessageBox.critical(parent, "导出失败", f"导出 PDF 时出错:\n{str(e)}")
