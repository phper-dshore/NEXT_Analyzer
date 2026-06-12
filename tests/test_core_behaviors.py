import os
import logging
import tempfile
import unittest

import numpy as np

from app.data_model import Measurement, Project, clip_interpolated_line
from app.export import (
    _create_cover_page,
    _create_summary_page,
    _evaluate_pair,
    _wrap_cover_value,
)
from app.s4p_parser import parse_s4p
from app.vna_controller import VNAController

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class S4PParserTests(unittest.TestCase):
    def test_rejects_incomplete_frequency_point(self):
        with tempfile.NamedTemporaryFile("w", suffix=".s4p", delete=False) as f:
            f.write("# HZ S RI R 50\n")
            f.write("1.0 0.1 0.0\n")
            path = f.name

        try:
            with self.assertRaisesRegex(ValueError, "Incomplete S4P data"):
                parse_s4p(path)
        finally:
            os.remove(path)


class FrequencyRangeTests(unittest.TestCase):
    def test_computes_next_only_inside_requested_frequency_range(self):
        frequencies = np.array([1e6, 10e6, 20e6, 30e6])
        s_params = np.zeros((4, 4, 4, 2), dtype=float)
        s_params[:, 2, 0, 0] = 0.1
        measurement = Measurement("test.s4p", 1, 2, frequencies, s_params)

        ranged_freq, ranged_next = Project().compute_next_in_range(
            measurement, 10e6, 20e6
        )

        np.testing.assert_array_equal(ranged_freq, np.array([10e6, 20e6]))
        self.assertEqual(len(ranged_next), 2)

    def test_limit_line_interpolates_requested_range_boundaries(self):
        frequencies = np.array([1e6, 100e6])
        values = np.array([-20.0, -40.0])

        clipped_freq, clipped_values = clip_interpolated_line(
            frequencies, values, 10e6, 20e6
        )

        np.testing.assert_array_equal(clipped_freq, np.array([10e6, 20e6]))
        np.testing.assert_allclose(
            clipped_values,
            np.interp(clipped_freq, frequencies, values),
        )


class VNAMeasurementTests(unittest.TestCase):
    def test_measurement_fails_when_vna_is_not_connected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pair_1_2.s4p")
            vna = VNAController()

            with self.assertLogs("app.vna_controller", level=logging.ERROR):
                result = vna.take_measurement(path, 10e6, 20e6, points=5)
            self.assertFalse(os.path.exists(path))

        self.assertEqual(result, "")


class ReportEvaluationTests(unittest.TestCase):
    def test_evaluation_clips_to_requested_frequency_range(self):
        frequencies = np.array([1e6, 2e6, 3e6])
        next_db = np.array([-40.0, -40.0, -20.0])
        limit_freqs = np.array([1e6, 3e6])
        limit_values = np.array([-30.0, -30.0])

        passed_all, *_ = _evaluate_pair(
            [("pair", frequencies, next_db)], limit_freqs, limit_values
        )
        passed_clipped, margin, worst_freq, *_ = _evaluate_pair(
            [("pair", frequencies, next_db)],
            limit_freqs,
            limit_values,
            freq_range=(1e6, 2e6),
        )

        self.assertFalse(passed_all)
        self.assertTrue(passed_clipped)
        self.assertEqual(margin, 10.0)
        self.assertIn(worst_freq, (1e6, 2e6))


class ReportCoverTests(unittest.TestCase):
    def test_cover_separator_stays_above_information_rows(self):
        figure = _create_cover_page(
            "HAITANG",
            "2026年06月09日",
            8,
            28,
            ["NEXT标准限值线"],
            "HTGSX20260609-001",
            "Rohde-Schwarz,ZNA67-4Port,1332450064101945,3.01",
            4.0,
        )

        separator_y = min(line.get_ydata()[0] for line in figure.artists)
        info_y = max(
            text.get_position()[1]
            for text in figure.texts
            if text.get_text().startswith("报告编号")
        )

        self.assertGreater(separator_y, info_y)

    def test_cover_wrap_avoids_a_single_character_tail(self):
        wrapped = _wrap_cover_value(
            "Rohde-Schwarz,ZNA67-4Port,1332450064101945,3.01 / "
            "Keysight Connection Expert TCPIP Instrument"
        )

        self.assertGreaterEqual(len(wrapped.splitlines()[-1]), 8)

    def test_summary_page_shows_pagination(self):
        figure = _create_summary_page(
            [], [], "HAITANG", summary_page_index=2, summary_page_count=3
        )

        self.assertTrue(any(
            text.get_text() == "综合测试结果 (2/3)"
            for text in figure.axes[0].texts
        ))

    def test_summary_page_fits_28_results_without_pagination_title(self):
        frequencies = np.array([1e6, 2e6])
        curves = [("SDD21", frequencies, np.array([-40.0, -40.0]))]
        pages = [(f"线对 {i}", curves) for i in range(1, 29)]
        limit_lines = [
            ("标准限值", frequencies, np.array([-30.0, -30.0]), "red", True)
        ]

        figure = _create_summary_page(pages, limit_lines, "HAITANG")
        texts = figure.axes[0].texts
        lowest_result_y = min(
            text.get_position()[1]
            for text in texts
            if text.get_text() == "PASS"
        )

        self.assertTrue(any(text.get_text() == "综合测试结果" for text in texts))
        self.assertGreater(lowest_result_y, 0.10)


class MainWindowDisplayTests(unittest.TestCase):
    def test_rebuild_tabs_adds_combined_display_first(self):
        from PyQt5.QtWidgets import QApplication
        from app.main_window import MainWindow
        from app import settings_manager

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        try:
            frequencies = np.array([1e6, 2e6])
            s_params = np.zeros((2, 4, 4, 2), dtype=float)
            s_params[:, 2, 0, 0] = 0.1
            window.project.measurements = [
                Measurement("pair_1_2.s4p", 1, 2, frequencies, s_params),
                Measurement("pair_1_3.s4p", 1, 3, frequencies, s_params),
            ]
            window.pair_config.set_loaded_combos({(1, 2), (1, 3)})
            window.pair_config._checkboxes[(1, 2)].setChecked(True)
            window.pair_config._checkboxes[(1, 3)].setChecked(True)
            window._rebuild_tabs()

            self.assertEqual(window.tab_widget.tabText(0), "合并显示")
            self.assertEqual(window.tab_widget.tabText(1), "线对 1-2")
            self.assertEqual(window.tab_widget.tabText(2), "线对 1-3")
        finally:
            window.close()
            if os.path.exists(settings_manager.SETTINGS_FILE):
                os.remove(settings_manager.SETTINGS_FILE)


if __name__ == "__main__":
    unittest.main()
