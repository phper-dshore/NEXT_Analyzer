"""
VNA controller module for controlling Keysight VNA via VISA/SCPI.

Requires:
- Keysight VISA (installed with Keysight Connection Expert) on Windows
- pyvisa Python package

If VISA is not available, the controller operates in simulation mode for testing.
"""

import os
import time
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# SCPI commands for Keysight PNA/ZNA series
SCPI_INIT = "*IDN?"
SCPI_TRIGGER = "INIT:IMM;*WAI"
SCPI_SET_FREQ_START = "SENS:FREQ:STAR {:.0f}"
SCPI_SET_FREQ_STOP = "SENS:FREQ:STOP {:.0f}"
SCPI_SET_POINTS = "SENS:SWE:POIN {:d}"
SCPI_SAVE_S4P = 'MMEM:STOR:SNP "{}", 4'
SCPI_SAVE_S4P_AUTO = 'MMEM:STOR:SNP:AUTO "{}", 4'

# Export format options
SCPI_EXPORT_FORMAT = 'MMEM:STOR:SNP:FORM {:s}'  # RI, DB, MA

# Try to import pyvisa; if not available, use simulation mode
try:
    import pyvisa
    _HAS_VISA = True
except ImportError:
    _HAS_VISA = False


class VNAController:
    """Controller for Keysight VNA via VISA/SCPI.

    Falls back to simulation mode when VISA is not available.
    """

    def __init__(self, resource_address: str = ""):
        self.resource_address = resource_address
        self.instrument = None
        self.rm = None
        self.connected = False
        self.simulation_mode = not _HAS_VISA
        self._id = ""
        self._sim_freq_start = 100e3
        self._sim_freq_stop = 500e6
        self._sim_points = 201

    def list_resources(self) -> list:
        """List available VISA resources."""
        if not _HAS_VISA:
            return ["Simulation: TCPIP0::192.168.1.100::inst0::INSTR (simulated)"]
        try:
            self.rm = pyvisa.ResourceManager()
            return self.rm.list_resources()
        except Exception as e:
            logger.warning(f"Failed to list VISA resources: {e}")
            return []

    def connect(self, resource_address: str = "") -> bool:
        """Connect to the VNA.

        Args:
            resource_address: VISA resource address (e.g. 'TCPIP0::192.168.1.100::inst0::INSTR')
                              If empty, uses previously set address.

        Returns:
            True if connected successfully.
        """
        if resource_address:
            self.resource_address = resource_address

        if not _HAS_VISA:
            self.simulation_mode = True
            self.connected = True
            self._id = "Simulated Keysight VNA (ZNA67)"
            logger.info(f"VISA not available, running in simulation mode")
            return True

        try:
            if self.rm is None:
                self.rm = pyvisa.ResourceManager()
            self.instrument = self.rm.open_resource(self.resource_address)
            self.instrument.timeout = 30000  # 30 second timeout

            # Query instrument identity
            idn = self.instrument.query(SCPI_INIT)
            self._id = idn.strip()
            self.connected = True
            self.simulation_mode = False
            logger.info(f"Connected to VNA: {self._id}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to VNA: {e}")
            self.connected = False
            self.simulation_mode = True
            self._id = f"Simulation (connection failed: {e})"
            return False

    def disconnect(self):
        """Disconnect from the VNA."""
        if self.instrument:
            try:
                self.instrument.close()
            except Exception:
                pass
        self.instrument = None
        self.connected = False

    def is_connected(self) -> bool:
        return self.connected

    def get_id(self) -> str:
        return self._id

    def configure_measurement(self, freq_start_hz: float, freq_stop_hz: float,
                              points: int = 1001):
        """Configure measurement parameters.

        Args:
            freq_start_hz: Start frequency in Hz.
            freq_stop_hz: Stop frequency in Hz.
            points: Number of sweep points.
        """
        if self.simulation_mode:
            logger.info(f"SIM: Configure measurement: {freq_start_hz/1e6:.1f}-"
                        f"{freq_stop_hz/1e6:.1f} MHz, {points} points")
            return

        if not self.connected:
            raise RuntimeError("VNA not connected")

        self._write(SCPI_SET_FREQ_START.format(freq_start_hz))
        self._write(SCPI_SET_FREQ_STOP.format(freq_stop_hz))
        self._write(SCPI_SET_POINTS.format(points))
        # Set format to dB/angle (Touchstone DB format)
        self._write(SCPI_EXPORT_FORMAT.format("DB"))
        # Store for simulation file generation
        self._sim_freq_start = freq_start_hz
        self._sim_freq_stop = freq_stop_hz
        self._sim_points = points

    def trigger_and_save(self, save_path: str) -> bool:
        """Trigger a measurement and save to S4P file.

        Args:
            save_path: Full path for the S4P file to save.

        Returns:
            True if measurement and save completed.
        """
        if self.simulation_mode:
            logger.info(f"SIM: Trigger measurement and save to {save_path}")
            # In simulation, create a placeholder file
            self._create_simulated_s4p(
                save_path,
                freq_start_hz=self._sim_freq_start,
                freq_stop_hz=self._sim_freq_stop,
                points=self._sim_points
            )
            return True

        if not self.connected:
            raise RuntimeError("VNA not connected")

        try:
            # Trigger single sweep
            self._write(SCPI_TRIGGER)

            # Save as S4P
            s4p_path = save_path.replace('/', '\\')  # Windows path
            self._write(SCPI_SAVE_S4P.format(s4p_path))

            # Wait briefly for file to be written
            time.sleep(0.5)
            return os.path.exists(save_path)
        except Exception as e:
            logger.error(f"Failed to trigger and save: {e}")
            return False

    def take_measurement(self, save_path: str,
                         freq_start_hz: float, freq_stop_hz: float,
                         points: int = 1001,
                         progress_callback: Optional[Callable] = None) -> bool:
        """Full measurement sequence: configure, trigger, save.

        Args:
            save_path: Full path for S4P file.
            freq_start_hz: Start frequency in Hz.
            freq_stop_hz: Stop frequency in Hz.
            points: Number of sweep points.
            progress_callback: Optional callback(current, total, message).

        Returns:
            True if successful.
        """
        try:
            if progress_callback:
                progress_callback(0, 3, "配置测量参数...")

            self.configure_measurement(freq_start_hz, freq_stop_hz, points)

            if progress_callback:
                progress_callback(1, 3, "触发测量...")

            result = self.trigger_and_save(save_path)

            if progress_callback:
                progress_callback(3, 3, "完成" if result else "失败")

            return result
        except Exception as e:
            logger.error(f"Measurement failed: {e}")
            if progress_callback:
                progress_callback(0, 3, f"错误: {e}")
            return False

    def _write(self, command: str):
        """Write a SCPI command to the VNA."""
        if self.instrument:
            self.instrument.write(command)

    def _create_simulated_s4p(self, filepath: str,
                              freq_start_hz: float = 100e3,
                              freq_stop_hz: float = 500e6,
                              points: int = 201):
        """Create a simulated S4P file for testing without VNA.

        Args:
            filepath: Output file path.
            freq_start_hz: Start frequency in Hz (default 100 kHz).
            freq_stop_hz: Stop frequency in Hz (default 500 MHz).
            points: Number of frequency points (default 201).
        """
        import numpy as np

        # Generate simulated 4-port S-parameters
        n_points = points
        freqs = np.linspace(freq_start_hz, freq_stop_hz, n_points)

        with open(filepath, 'w') as f:
            f.write("! Simulated S4P file for testing\n")
            f.write("# HZ S DB R 50\n")

            for freq in freqs:
                f_mhz = freq / 1e6
                # Create realistic-looking S-parameters
                s11_db = -20 - 5 * np.random.random()
                s11_ang = np.random.uniform(-180, 180)
                s21_db = -1 - 0.01 * f_mhz - 2 * np.random.random()
                s21_ang = np.random.uniform(-180, 180)

                # NEXT decreases with frequency (gets worse)
                next_db = -60 + 20 * (f_mhz / 500) + 2 * np.random.random()

                vals = [freq, s11_db, s11_ang]

                # Generate 16 S-parameters in standard Touchstone order
                # For simplicity, fill with reasonable values
                idx = 0
                for col in range(4):  # input port
                    for row in range(4):  # output port
                        if idx == 0:
                            pass  # S11 already done
                        elif idx == 1:  # S21
                            vals.extend([s21_db, s21_ang])
                        elif idx == 4:  # S12
                            vals.extend([s21_db, s21_ang])  # reciprocal
                        elif idx == 5:  # S22
                            vals.extend([s11_db, s11_ang])
                        elif (row, col) in [(2, 0), (3, 0), (2, 1), (3, 1)]:
                            # NEXT paths
                            vals.extend([next_db, np.random.uniform(-180, 180)])
                        else:
                            vals.extend([-80 - 10 * np.random.random(),
                                         np.random.uniform(-180, 180)])
                        idx += 1

                f.write(" ".join(f"{v:.6e}" if isinstance(v, float) and v > 1e6
                                 else f"{v:.6f}" for v in vals) + "\n")


def find_visa_resources() -> list:
    """Helper to find available VISA instruments.

    Returns:
        List of resource strings (e.g. 'TCPIP0::192.168.1.100::inst0::INSTR').
    """
    ctrl = VNAController()
    return ctrl.list_resources()
