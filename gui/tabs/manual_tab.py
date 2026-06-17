import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox,
    QLabel, QDoubleSpinBox, QSpinBox, QComboBox,
    QPushButton, QMessageBox,
)
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont

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

        grp2 = QGroupBox("Manual Spectrometer")
        g2 = QVBoxLayout(grp2)
        btn_single = QPushButton("Acquire Single Spectrum")
        btn_single.clicked.connect(self._preview_spectrum)
        g2.addWidget(btn_single)
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
            self.sig_plot.emit(None, wl, corr)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))