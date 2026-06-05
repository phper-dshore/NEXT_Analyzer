"""
Data models for the S4P analyzer application.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import numpy as np


@dataclass
class Measurement:
    """Represents one S4P test measurement covering two pairs.

    The 4-port VNA measures two cable pairs at a time:
    - Ports 1-2 are connected to pair_a
    - Ports 3-4 are connected to pair_b
    """
    file_path: str
    pair_a: int       # Pair number on ports 1-2
    pair_b: int       # Pair number on ports 3-4
    frequencies: np.ndarray  # Frequency array in Hz
    s_params: np.ndarray     # Shape (n_freqs, 4, 4, 2) - S-parameter matrix [real, imag]


@dataclass
class LimitLine:
    """A user-defined limit/spec line for comparison."""
    name: str
    points: List[Tuple[float, float]]  # List of (frequency_Hz, amplitude_dB)
    color: str = 'red'
    visible: bool = True


@dataclass
class Project:
    """The main project data model."""
    total_pairs: int = 8
    measurements: List[Measurement] = field(default_factory=list)
    limit_lines: List[LimitLine] = field(default_factory=list)
    display_freq_start: float = 100e3    # Hz - display frequency range start
    display_freq_stop: float = 500e6     # Hz - display frequency range stop

    @property
    def test_combinations(self) -> List[Tuple[int, int]]:
        """Get all pair combinations that need to be tested, ordered."""
        combos = []
        for i in range(1, self.total_pairs + 1):
            for j in range(i + 1, self.total_pairs + 1):
                combos.append((i, j))
        return combos

    def add_measurement(self, measurement: Measurement):
        """Add a measurement and ensure pair numbers are within range."""
        if measurement.pair_a > self.total_pairs or measurement.pair_b > self.total_pairs:
            raise ValueError(
                f"Pair number exceeds total pairs ({self.total_pairs}): "
                f"pair_a={measurement.pair_a}, pair_b={measurement.pair_b}"
            )
        if measurement.pair_a == measurement.pair_b:
            raise ValueError(
                f"pair_a and pair_b must be different, got both={measurement.pair_a}"
            )
        self.measurements.append(measurement)

    def get_pair_combinations(self) -> List[Tuple[int, int]]:
        """Get all (a, b) pair combinations that have measurements, where a < b."""
        combos = set()
        for m in self.measurements:
            a, b = (m.pair_a, m.pair_b) if m.pair_a < m.pair_b else (m.pair_b, m.pair_a)
            combos.add((a, b))
        return sorted(combos)

    def get_all_expected_combinations(self) -> List[Tuple[int, int]]:
        """Get all possible pair combinations for the total number of pairs."""
        combos = []
        for i in range(1, self.total_pairs + 1):
            for j in range(i + 1, self.total_pairs + 1):
                combos.append((i, j))
        return combos

    def get_measurement_for_pairs(self, pair_a: int, pair_b: int) -> Optional[Measurement]:
        """Find the measurement covering the given pair combination."""
        for m in self.measurements:
            if {m.pair_a, m.pair_b} == {pair_a, pair_b}:
                return m
        return None

    def compute_next(self, measurement: Measurement, method: str = 'power_sum') -> np.ndarray:
        """Compute NEXT (Near-End Crosstalk) for a measurement.

        Args:
            measurement: The measurement to compute NEXT for.
            method: 'power_sum' (default) or 'worst_case'.

        For 4-port measurement where pair A is on ports 1-2 and pair B is on ports 3-4:
        - NEXT paths: S31 (port1→port3), S41 (port1→port4), S32 (port2→port3), S42 (port2→port4)
        - Power sum: 10*log10(10^(S31/10) + 10^(S41/10) + 10^(S32/10) + 10^(S42/10))
        - Worst case: max(S31, S41, S32, S42)

        Returns:
            ndarray of NEXT values in dB.
        """
        s31 = self._get_s_db(measurement, 3, 1)
        s41 = self._get_s_db(measurement, 4, 1)
        s32 = self._get_s_db(measurement, 3, 2)
        s42 = self._get_s_db(measurement, 4, 2)

        if method == 'worst_case':
            return np.maximum.reduce([s31, s41, s32, s42])
        else:  # power_sum
            linear = 10 ** (s31 / 10) + 10 ** (s41 / 10) + 10 ** (s32 / 10) + 10 ** (s42 / 10)
            return 10 * np.log10(linear)

    def compute_next_single(self, measurement: Measurement, tx_port: int, rx_port: int) -> np.ndarray:
        """Compute NEXT for a single S-parameter path between tx_port and rx_port."""
        return self._get_s_db(measurement, rx_port, tx_port)

    @staticmethod
    def _get_s_db(measurement: Measurement, port_i: int, port_j: int) -> np.ndarray:
        """Get S-parameter magnitude in dB (1-indexed ports)."""
        row, col = port_i - 1, port_j - 1
        real_part = measurement.s_params[:, row, col, 0]
        imag_part = measurement.s_params[:, row, col, 1]
        mag = np.sqrt(real_part ** 2 + imag_part ** 2)
        return np.where(mag > 0, 20 * np.log10(mag), -200)
