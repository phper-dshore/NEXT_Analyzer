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
    - ports_a are connected to pair_a
    - ports_b are connected to pair_b
    """
    file_path: str
    pair_a: int       # Logical pair number for ports_a
    pair_b: int       # Logical pair number for ports_b
    frequencies: np.ndarray  # Frequency array in Hz
    s_params: np.ndarray     # Shape (n_freqs, 4, 4, 2) - S-parameter matrix [real, imag]
    ports_a: Tuple[int, int] = (1, 2)  # VNA ports belonging to pair_a
    ports_b: Tuple[int, int] = (3, 4)  # VNA ports belonging to pair_b


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
    port_group_a: Tuple[int, int] = (1, 2)  # VNA ports for the first cable pair
    port_group_b: Tuple[int, int] = (3, 4)  # VNA ports for the second cable pair
    report_number: str = ""  # Report number, e.g. "HTGSX20260608-001"
    device_model: str = ""   # VNA device model name

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

    def compute_next(self, measurement: Measurement, method: str = 'sdd21') -> np.ndarray:
        """Compute NEXT (Near-End Crosstalk) for a measurement.

        Args:
            measurement: The measurement to compute NEXT for.
            method: 'sdd21' (default, differential), 'power_sum', or 'worst_case'.

        Uses the VNA port groups from the measurement (which ports belong to each pair).
        NEXT is the crosstalk between port_group_a and port_group_b.
        - SDD21: differential crosstalk 0.5*(S31-S32-S41+S42) in dB
        - Power sum: 10*log10(sum(10^(S_ij/10))) over all cross-group paths
        - Worst case: max(S_ij) over all cross-group paths

        Returns:
            ndarray of NEXT values in dB.
        """
        pa1, pa2 = measurement.ports_a
        pb1, pb2 = measurement.ports_b

        if method == 'sdd21':
            # Differential NEXT (mixed-mode S-parameter)
            s31 = self._get_s_complex(measurement, pb1, pa1)
            s32 = self._get_s_complex(measurement, pb1, pa2)
            s41 = self._get_s_complex(measurement, pb2, pa1)
            s42 = self._get_s_complex(measurement, pb2, pa2)
            sdd21 = 0.5 * (s31 - s32 - s41 + s42)
            mag = np.abs(sdd21)
            return np.where(mag > 0, 20 * np.log10(mag), -200)

        # All S-parameters from ports_a to ports_b (magnitude in dB)
        paths = [
            self._get_s_db(measurement, pb1, pa1),
            self._get_s_db(measurement, pb2, pa1),
            self._get_s_db(measurement, pb1, pa2),
            self._get_s_db(measurement, pb2, pa2),
        ]
        if method == 'worst_case':
            return np.maximum.reduce(paths)
        else:  # power_sum
            linear = sum(10 ** (p / 10) for p in paths)
            return 10 * np.log10(linear)

    def compute_next_single(self, measurement: Measurement, tx_port: int, rx_port: int) -> np.ndarray:
        """Compute NEXT for a single S-parameter path between tx_port and rx_port."""
        return self._get_s_db(measurement, rx_port, tx_port)

    @staticmethod
    def _get_s_complex(measurement: Measurement, port_i: int, port_j: int) -> np.ndarray:
        """Get S-parameter as complex number (1-indexed ports)."""
        row, col = port_i - 1, port_j - 1
        real_part = measurement.s_params[:, row, col, 0]
        imag_part = measurement.s_params[:, row, col, 1]
        return real_part + 1j * imag_part

    @staticmethod
    def _get_s_db(measurement: Measurement, port_i: int, port_j: int) -> np.ndarray:
        """Get S-parameter magnitude in dB (1-indexed ports)."""
        row, col = port_i - 1, port_j - 1
        real_part = measurement.s_params[:, row, col, 0]
        imag_part = measurement.s_params[:, row, col, 1]
        mag = np.sqrt(real_part ** 2 + imag_part ** 2)
        return np.where(mag > 0, 20 * np.log10(mag), -200)
