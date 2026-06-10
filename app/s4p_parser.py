"""
Touchstone .s4p file parser for 4-port S-parameter data.

Supports:
- Format: RI (real/imaginary) and DB (magnitude/angle in dB/degrees)
- Impedance: 50Ω and others
- Frequency units: Hz, kHz, MHz, GHz
"""

import numpy as np


class S4PParser:
    """Parse Touchstone format .s4p files."""

    FREQ_MULTIPLIERS = {
        'hz': 1,
        'khz': 1e3,
        'mhz': 1e6,
        'ghz': 1e9,
    }

    def __init__(self):
        self.frequencies = None  # Hz
        self.s_params = None     # ndarray of shape (n_freq, 4, 4, 2) where last dim is [real, imag]
        self.impedance = 50.0
        self.parameter = 'S'
        self.format = 'RI'
        self.comments = []

    def parse(self, filepath):
        """Parse an .s4p file and populate the data arrays.

        Args:
            filepath: Path to the .s4p file.

        Returns:
            self for chaining.

        Raises:
            ValueError: If the file format is invalid or unsupported.
            IOError: If the file cannot be read.
        """
        self.comments = []
        raw_lines = self._read_file(filepath)
        data_lines = self._parse_header(raw_lines)
        self._parse_data(data_lines)
        return self

    def _read_file(self, filepath):
        """Read file and strip comments/blank lines, preserving line content."""
        with open(filepath, 'r') as f:
            lines = f.readlines()

        # Strip trailing whitespace/newline, keep leading whitespace (shouldn't exist but just in case)
        return [line.rstrip('\n\r') for line in lines]

    def _parse_header(self, lines):
        """Parse the option line and comments. Return data lines."""
        data_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith('!'):
                self.comments.append(stripped)
                continue
            if stripped.startswith('#'):
                self._parse_option_line(stripped)
                data_start = i + 1
                break
            if stripped[0] in '+-0123456789.':
                # No option line - default Touchstone format
                data_start = i
                break
        else:
            raise ValueError("No data found in file")

        return lines[data_start:]

    def _parse_option_line(self, line):
        """Parse the option line: # HZ S RI R 50"""
        parts = line.strip().split()
        if len(parts) < 1:
            return

        # parts[0] should be '#'
        tokens = parts[1:]

        # Defaults
        freq_unit = 'hz'
        self.parameter = 'S'
        self.format = 'RI'
        self.impedance = 50.0

        i = 0
        while i < len(tokens):
            token = tokens[i].upper()
            if token in ('HZ', 'KHZ', 'MHZ', 'GHZ'):
                freq_unit = token.lower()
            elif token in ('S', 'Y', 'Z', 'G', 'H'):
                self.parameter = token
            elif token in ('RI', 'DB', 'MA'):
                self.format = token
            elif token == 'R':
                i += 1
                if i < len(tokens):
                    try:
                        self.impedance = float(tokens[i])
                    except ValueError:
                        pass
            i += 1

        self._freq_multiplier = self.FREQ_MULTIPLIERS.get(freq_unit, 1)

    def _parse_data(self, data_lines):
        """Parse the numeric data lines into frequencies and S-parameter matrix."""
        # Collect all numeric tokens
        all_numbers = []
        for line in data_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('!'):
                continue
            # Split on whitespace and try to parse numbers
            tokens = stripped.split()
            for token in tokens:
                try:
                    val = float(token)
                    all_numbers.append(val)
                except ValueError:
                    # Skip non-numeric tokens (shouldn't happen in data section)
                    continue

        # For S4P: each frequency point has: 1 freq + 16 complex values (32 reals) for RI
        # or 1 freq + 16 (mag,angle) pairs (32 reals) for DB/MA
        # S4P has 4 ports -> 4x4 = 16 S-parameters
        # In RI format: freq, S11re, S11im, S12re, S12im, ..., S44re, S44im
        # In DB format: freq, S11db, S11ang, S12db, S12ang, ..., S44db, S44ang

        values_per_freq = 1 + 16 * 2  # freq + 16 complex numbers (each = 2 values)

        if len(all_numbers) % values_per_freq != 0:
            raise ValueError(
                "Incomplete S4P data: expected each frequency point to contain "
                f"{values_per_freq} numeric values, got {len(all_numbers)} total"
            )

        n_complete = len(all_numbers) // values_per_freq
        n_freqs = n_complete

        if n_freqs == 0:
            raise ValueError(f"Could not parse any frequency points from {len(all_numbers)} numbers")

        freqs = []
        s_params = np.zeros((n_freqs, 4, 4, 2), dtype=float)

        for i in range(n_freqs):
            base = i * values_per_freq
            freq_hz = all_numbers[base] * self._freq_multiplier
            freqs.append(freq_hz)

            # Extract 16 complex values
            idx = base + 1
            for row in range(4):
                for col in range(4):
                    real_or_mag = all_numbers[idx]
                    imag_or_ang = all_numbers[idx + 1]
                    idx += 2

                    if self.format == 'RI':
                        s_params[i, row, col, 0] = real_or_mag  # real
                        s_params[i, row, col, 1] = imag_or_ang  # imag
                    elif self.format == 'DB':
                        # Magnitude in dB, angle in degrees
                        mag_linear = 10 ** (real_or_mag / 20.0)
                        ang_rad = np.deg2rad(imag_or_ang)
                        s_params[i, row, col, 0] = mag_linear * np.cos(ang_rad)  # real
                        s_params[i, row, col, 1] = mag_linear * np.sin(ang_rad)  # imag
                    elif self.format == 'MA':
                        # Magnitude linear, angle in degrees
                        ang_rad = np.deg2rad(imag_or_ang)
                        s_params[i, row, col, 0] = real_or_mag * np.cos(ang_rad)
                        s_params[i, row, col, 1] = real_or_mag * np.sin(ang_rad)

        self.frequencies = np.array(freqs)
        self.s_params = s_params
        return self

    def get_s_dB(self, port_i, port_j):
        """Get S-parameter magnitude in dB for the given port pair (1-indexed).

        Args:
            port_i: Output port number (1-4)
            port_j: Input port number (1-4)

        Returns:
            ndarray of magnitude values in dB.
        """
        row, col = port_i - 1, port_j - 1
        real_part = self.s_params[:, row, col, 0]
        imag_part = self.s_params[:, row, col, 1]
        mag = np.sqrt(real_part ** 2 + imag_part ** 2)
        # Avoid log10(0)
        mag_db = np.where(mag > 0, 20 * np.log10(mag), -200)
        return mag_db


def parse_s4p(filepath):
    """Convenience function to parse an .s4p file.

    Args:
        filepath: Path to the .s4p file.

    Returns:
        (frequencies, s_params) tuple where frequencies is ndarray of shape (n_freqs,)
        in Hz, and s_params is ndarray of shape (n_freqs, 4, 4, 2) (last dim: real, imag).
    """
    parser = S4PParser()
    parser.parse(filepath)
    return parser.frequencies, parser.s_params
