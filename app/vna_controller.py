"""
VNA controller module for R&S ZNA67 via VISA/SCPI.

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

# SCPI commands for Rohde & Schwarz ZNA67
SCPI_INIT = "*IDN?"
SCPI_TRIGGER = "INIT:IMM;*WAI"
SCPI_SET_FREQ_START = "SENS:FREQ:STAR {:.0f}"
SCPI_SET_FREQ_STOP = "SENS:FREQ:STOP {:.0f}"
SCPI_SET_POINTS = "SENS:SWE:POIN {:d}"
# R&S ZNA format: :MMEMory:STORe:TRACe:PORTS <trace>, '<path>', COMPlex, <ports...>
SCPI_SAVE_S4P = ':MMEM:STOR:TRAC:PORT 1, \'{}\', COMP, 1,2,3,4'

# Export format options
SCPI_EXPORT_FORMAT = 'MMEM:STOR:SNP:FORM {:s}'  # RI, DB, MA

# Try to import pyvisa; if not available, use simulation mode
try:
    import pyvisa
    _HAS_VISA = True
except ImportError:
    _HAS_VISA = False


class VNAController:
    """Controller for R&S ZNA67 VNA via VISA/SCPI.

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
        # VNA local save path (e.g. C:\\HPData\\) — set by wizard config
        self.vna_local_path = "C:\\HPData\\"

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
            self._id = "Simulated Rohde & Schwarz ZNA67"
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

            # Auto-detect if ZNA67: use :MMEM:STOR:TRAC:PORT command
            if 'ZNA' in self._id.upper():
                logger.info("Detected R&S ZNA series VNA")

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

    def trigger_and_save(self, save_path: str) -> str:
        """Trigger a measurement and save S4P file.

        The VNA writes the S4P file via SCPI to its local drive,
        then the PC reads the file from the UNC network share path.

        Args:
            save_path: UNC path for the S4P file to read from
                       (e.g. \\\\100.1.1.1\\HPData\\pair_1_2.s4p).

        Returns:
            Path to the saved S4P file on success, or empty string on failure.
        """
        if self.simulation_mode:
            logger.info(f"SIM: Trigger measurement and save to {save_path}")
            self._create_simulated_s4p(
                save_path,
                freq_start_hz=self._sim_freq_start,
                freq_stop_hz=self._sim_freq_stop,
                points=self._sim_points
            )
            return save_path

        if not self.connected:
            raise RuntimeError("VNA not connected")

        try:
            # Build VNA local path from UNC path
            # UNC: \\100.1.1.1\HPData\pair_1_2.s4p
            # VNA local: C:\HPData\pair_1_2.s4p
            filename = os.path.basename(save_path)
            vna_filepath = os.path.join(self.vna_local_path, filename)

            # Trigger single sweep
            self._write(SCPI_TRIGGER)

            # Save S4P on VNA using R&S ZNA command with local path
            logger.info(f"VNA save command: {SCPI_SAVE_S4P.format(vna_filepath)}")
            self._write(SCPI_SAVE_S4P.format(vna_filepath))

            # Wait for file to be written
            time.sleep(3)

            # Verify file exists on the UNC share (VNA writes to its local
            # C: drive, which is shared as a network share)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                return save_path

            logger.error(f"S4P file not found after save: {save_path}")
            return ""
        except Exception as e:
            logger.error(f"Failed to trigger and save: {e}")
            return ""

    def take_measurement(self, save_path: str,
                         freq_start_hz: float, freq_stop_hz: float,
                         points: int = 1001,
                         progress_callback: Optional[Callable] = None) -> str:
        """Full measurement sequence: configure, trigger, get file path.

        Args:
            save_path: Full UNC path for the S4P file (e.g. \\\\100.1.1.1\\HPData\\pair.s4p).
            freq_start_hz: Start frequency in Hz.
            freq_stop_hz: Stop frequency in Hz.
            points: Number of sweep points.
            progress_callback: Optional callback(current, total, message).

        Returns:
            Path to the S4P file on success, empty string on failure.
        """
        try:
            if progress_callback:
                progress_callback(0, 3, "配置测量参数...")

            self.configure_measurement(freq_start_hz, freq_stop_hz, points)

            if progress_callback:
                progress_callback(1, 3, "触发测量...")

            if progress_callback:
                progress_callback(2, 3, "保存 S4P 文件...")

            result_path = self.trigger_and_save(save_path)

            if progress_callback:
                progress_callback(3, 3, "完成" if result_path else "失败")

            return result_path
        except Exception as e:
            logger.error(f"Measurement failed: {e}")
            if progress_callback:
                progress_callback(0, 3, f"错误: {e}")
            return ""

    def _write(self, command: str):
        """Write a SCPI command to the VNA."""
        if self.instrument:
            logger.debug(f"SCPI write: {command}")
            self.instrument.write(command)

    def _query(self, command: str) -> str:
        """Write a SCPI command and read the response."""
        if self.instrument:
            logger.debug(f"SCPI query: {command}")
            return self.instrument.query(command)
        return ""

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
