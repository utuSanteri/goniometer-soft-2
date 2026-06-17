import logging
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox,
    QLabel, QDoubleSpinBox, QSpinBox, QComboBox,
    QPushButton, QMessageBox, QFileDialog,
)
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont

from gui.hw_imports import SourceMeterError


log = logging.getLogger(__name__)


class ManualTab(QWidget):
    """Manual motor jog, position, and single-spectrum acquisition."""

    sig_plot = pyqtSignal(object, object, object)   # angle, wl, counts

    def __init__(self, hw, cfg, get_subtract_dark, parent=None):
        """
        Parameters
        ----------
        get_subtract_dark : callable() -> bool
            Returns the current state of the dark-subtraction checkbox
            (lives on the Spectrometer tab).
        """
        super().__init__(parent)
        self.hw  = hw
        self.cfg = cfg
        self._get_subtract_dark = get_subtract_dark
        self._last_spectrum = None
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)

        grp = QGroupBox("Manual Motor Control")
        g = QGridLayout(grp)

        g.addWidget(QLabel("Motor:"), 0, 0)
        self.cmb_man_motor = QComboBox()
        self.cmb_man_motor.addItems(["1", "2"])
        g.addWidget(self.cmb_man_motor, 0, 1)

        g.addWidget(QLabel("Degrees:"), 1, 0)
        self.spn_man_deg = QDoubleSpinBox()
        self.spn_man_deg.setRange(0.01, 360)
        self.spn_man_deg.setValue(5.0)
        g.addWidget(self.spn_man_deg, 1, 1)
        btn_fwd = QPushButton("▶  Move Forward (+)")
        btn_fwd.clicked.connect(lambda: self._manual_move(1))
        btn_rev = QPushButton("◀  Move Reverse (−)")
        btn_rev.clicked.connect(lambda: self._manual_move(-1))
        g.addWidget(btn_fwd, 2, 0)
        g.addWidget(btn_rev, 2, 1)

        btn_stop = QPushButton("⬛  STOP Motors")
        btn_stop.setStyleSheet(
            "background-color: #e67e22; color: white; font-weight: bold")
        btn_stop.clicked.connect(self._stop_motors)
        g.addWidget(btn_stop, 3, 0, 1, 2)

        btn_zero = QPushButton("Set Current Position as Zero")
        btn_zero.clicked.connect(self._zero_motors)
        g.addWidget(btn_zero, 4, 0, 1, 2)

        btn_home = QPushButton("Go to Home (Zero)")
        btn_home.clicked.connect(self._home_motors)
        g.addWidget(btn_home, 5, 0, 1, 2)

        g.addWidget(QLabel("Motor Speed (steps/s):"), 6, 0)
        self.spn_speed = QSpinBox()
        self.spn_speed.setRange(1, 10000)
        self.spn_speed.setValue(
            self.cfg["motors"]["max_speed_steps_per_sec"])
        btn_speed = QPushButton("Set Speed")
        btn_speed.clicked.connect(self._set_speed)
        g.addWidget(self.spn_speed, 6, 1)
        g.addWidget(btn_speed, 7, 0, 1, 2)

        self.lbl_pos = QLabel("Position: —")
        self.lbl_pos.setFont(QFont("Courier", 10))
        g.addWidget(self.lbl_pos, 8, 0, 1, 2)

        btn_update_pos = QPushButton("Refresh Position")
        btn_update_pos.clicked.connect(self._refresh_position)
        g.addWidget(btn_update_pos, 9, 0, 1, 2)
        lay.addWidget(grp)

        grp2 = QGroupBox("Manual Spectrometer and Source Output Control")
        g2 = QVBoxLayout(grp2)
        btn_single = QPushButton("Acquire Single Spectrum")
        btn_single.clicked.connect(self._preview_spectrum)
        self.btn_out_on = QPushButton("Output ON")
        self.btn_out_on.setStyleSheet(
            "background-color: #2ecc71; color: white; font-weight: bold")
        self.btn_out_on.clicked.connect(self._output_on)
        self.btn_out_off = QPushButton("Output OFF")
        self.btn_out_off.setStyleSheet(
            "background-color: #e74c3c; color: white; font-weight: bold")
        self.btn_out_off.clicked.connect(self._output_off)
        self.btn_savedialog = QPushButton("Save Last Spectrum")
        self.btn_savedialog.clicked.connect(self._save_spectrum)
        g2.addWidget(self.btn_out_on)
        g2.addWidget(self.btn_out_off)
        g2.addWidget(btn_single)
        g2.addWidget(self.btn_savedialog)
        lay.addWidget(grp2)




        lay.addStretch()

    # ── Handlers ──────────────────────────────────────────────────────
    def _manual_move(self, sign: int):
        if not self.hw.motor:
            QMessageBox.warning(self, "Warning", "Motor not connected")
            return
        try:
            motor_id = int(self.cmb_man_motor.currentText())
            deg = sign * self.spn_man_deg.value()
            self.hw.motor.move_degrees(motor_id, deg)
            self._refresh_position()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _stop_motors(self):
        if self.hw.motor:
            self.hw.motor.stop()

    def _zero_motors(self):
        if self.hw.motor:
            self.hw.motor.zero()
            self.lbl_pos.setText("Position: zeroed")

    def _home_motors(self):
        if self.hw.motor:
            try:
                self.hw.motor.home()
                self._refresh_position()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _set_speed(self):
        if self.hw.motor:
            self.hw.motor.set_speed(self.spn_speed.value())

    def _refresh_position(self):
        if self.hw.motor:
            try:
                p1, p2 = self.hw.motor.get_position()
                spd = self.hw.motor.steps_per_degree
                self.lbl_pos.setText(
                    f"M1: {p1} steps ({p1/spd:.2f}°)  "
                    f"M2: {p2} steps ({p2/spd:.2f}°)")
            except Exception as e:
                log.error("Position query failed: %s", e)

    def _preview_spectrum(self):
        if not self.hw.spec:
            QMessageBox.warning(
                self, "Warning", "Spectrometer not connected")
            return
        try:
            wl, _raw, corr = self.hw.spec.acquire(
                subtract_dark=self._get_subtract_dark())
            self._last_spectrum = (wl, _raw, corr)
            self.sig_plot.emit(None, wl, corr)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def _output_on(self):
        if not self.hw.source:
            QMessageBox.warning(
                self, "Warning", "Source meter not connected")
            return
        try:
            self.hw.source.output_on()
            log.info("Output ON")
        except SourceMeterError as e:
            self.hw.source.output_off()
            QMessageBox.critical(
                self,
                "Verification Failed — Output Disabled",
                f"{e}\n\nThe output has been turned off automatically.",
            )
            log.error("Output ON verification failed: %s", e)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            log.error("Output ON failed: %s", e)

    def _output_off(self):
        if self.hw.source:
            try:
                self.hw.source.output_off()
                log.info("Output OFF")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
    


    def _save_spectrum(self):
        if self._last_spectrum is None:
            QMessageBox.warning(self, "No Data", "Acquire a spectrum first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Spectrum", "", "Text files (*.txt);;CSV files (*.csv)")
        if not path:
            return

        wl, raw, corr = self._last_spectrum
        delimiter = ";"
        now = datetime.now().isoformat()

        header = [
            f"# Spectrum",
            f"# Date             : {now}",
            f"# Integration time : {self.hw.spec.integration_time_ms} ms",
            f"# Scans averaged   : {self.hw.spec.scans_to_average}",
            f"# Boxcar width     : {self.hw.spec.boxcar_width}",
            f"# Dark subtracted  : {self.hw.spec.has_dark()}",
        ]

        # Source parameters are optional — only written if connected
        if self.hw.source and self.hw.source.is_connected():
            header += [
                f"# Source mode      : {self.hw.source.source_mode}",
                f"# Voltage          : {self.hw.source.voltage} V",
                f"# Current limit    : {self.hw.source.current_limit} A",
            ]

        header += [
            f"#",
            f"# Row 0 : Wavelengths (nm)",
            f"# Row 1 : Raw counts",
            f"# Row 2 : Corrected counts",
        ]

        with open(path, "w") as f:
            f.write("\n".join(header) + "\n")
            f.write(delimiter.join(f"{w:.4f}" for w in wl) + "\n")
            f.write(delimiter.join(f"{v:.6g}" for v in raw) + "\n")
            f.write(delimiter.join(f"{v:.6g}" for v in corr) + "\n")

        log.info("Spectrum saved to %s", path)