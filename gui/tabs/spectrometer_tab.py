import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QGroupBox,
    QLabel, QDoubleSpinBox, QSpinBox, QCheckBox,
    QPushButton, QMessageBox,
)
from PyQt5.QtCore import pyqtSignal

log = logging.getLogger(__name__)


class SpectrometerTab(QWidget):
    """Acquisition settings, dark spectrum, preview."""

    sig_plot = pyqtSignal(object, object, object)   # angle, wl, counts

    def __init__(self, hw, cfg, parent=None):
        super().__init__(parent)
        self.hw  = hw
        self.cfg = cfg
        # (integration ms, averages, boxcar) the stored dark was taken
        # with. The dark is only valid for exactly these settings.
        self._dark_settings = None
        self._build_ui()

    @property
    def subtract_dark(self) -> bool:
        return self.chk_dark.isChecked()

    # ── UI ────────────────────────────────────────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)

        grp = QGroupBox("Acquisition Settings")
        g = QGridLayout(grp)

        g.addWidget(QLabel("Integration time (ms):"), 0, 0)
        self.spn_inttime = QDoubleSpinBox()
        self.spn_inttime.setRange(
            self.cfg["spectrometer"].get("min_integration_time_ms", 3), 60000)
        self.spn_inttime.setValue(
            self.cfg["spectrometer"]["default_integration_time_ms"])
        self.spn_inttime.valueChanged.connect(self.apply_settings)
        g.addWidget(self.spn_inttime, 0, 1)

        g.addWidget(QLabel("Scans to average:"), 1, 0)
        self.spn_avg = QSpinBox()
        self.spn_avg.setRange(1, 100)
        self.spn_avg.setValue(
            self.cfg["spectrometer"]["default_scans_to_average"])
        self.spn_avg.valueChanged.connect(self.apply_settings)
        g.addWidget(self.spn_avg, 1, 1)

        g.addWidget(QLabel("Boxcar width:"), 2, 0)
        self.spn_boxcar = QSpinBox()
        self.spn_boxcar.setRange(0, 20)
        self.spn_boxcar.setValue(
            self.cfg["spectrometer"]["default_boxcar_width"])
        self.spn_boxcar.valueChanged.connect(self.apply_settings)
        g.addWidget(self.spn_boxcar, 2, 1)

        # Apply on Enter / focus-out / arrow step only, not on every
        # keystroke (clearing a digit mid-edit used to raise "too low")
        for spn in (self.spn_inttime, self.spn_avg, self.spn_boxcar):
            spn.setKeyboardTracking(False)

        self.chk_dark = QCheckBox("Subtract dark spectrum")
        self.chk_dark.setChecked(True)
        g.addWidget(self.chk_dark, 3, 0, 1, 2)
        lay.addWidget(grp)

        grp2 = QGroupBox("Dark Spectrum")
        g2 = QVBoxLayout(grp2)
        self.btn_collect_dark = QPushButton("Collect Dark Now")
        self.btn_collect_dark.clicked.connect(self._collect_dark)
        g2.addWidget(self.btn_collect_dark)
        self.btn_clear_dark = QPushButton("Clear Dark")
        self.btn_clear_dark.clicked.connect(self._clear_dark)
        g2.addWidget(self.btn_clear_dark)
        self.lbl_dark_status = QLabel("No dark spectrum")
        g2.addWidget(self.lbl_dark_status)
        lay.addWidget(grp2)

        grp3 = QGroupBox("Preview")
        g3 = QVBoxLayout(grp3)
        self.btn_preview = QPushButton("Acquire Preview Spectrum")
        self.btn_preview.clicked.connect(self._preview_spectrum)
        g3.addWidget(self.btn_preview)
        lay.addWidget(grp3)

        lay.addStretch()

    # ── Public ────────────────────────────────────────────────────────
    def apply_settings(self) -> bool:
        """Pushes the spinner values to the spectrometer. Returns False if
        a value was rejected; the spinner then reverts to the last valid
        value."""
        if not self.hw.spec:
            return True
        ok = True
        try:
            self.hw.spec.set_scans_to_average(self.spn_avg.value())
            self.hw.spec.set_boxcar_width(self.spn_boxcar.value())
            self.hw.spec.set_integration_time(self.spn_inttime.value())
        except ValueError as e:
            ok = False
            QMessageBox.warning(
                self, "Integration Time Out of Range", str(e))
        except Exception as e:
            ok = False
            QMessageBox.critical(self, "Spectrometer Error", str(e))

        # Show what the device is actually using
        self.spn_inttime.blockSignals(True)
        self.spn_inttime.setValue(self.hw.spec.integration_time_ms)
        self.spn_inttime.blockSignals(False)

        self._check_dark_settings()
        return ok

    # ── Private ───────────────────────────────────────────────────────
    def _current_settings(self) -> tuple:
        s = self.hw.spec
        return (s.integration_time_ms, s.scans_to_average, s.boxcar_width)

    def _check_dark_settings(self):
        """Clears the dark if the acquisition settings no longer match
        the ones it was taken with."""
        if self._dark_settings is None or not self.hw.spec.has_dark():
            return
        if self._current_settings() == self._dark_settings:
            return
        self.hw.spec.clear_dark()
        self._dark_settings = None
        self.lbl_dark_status.setText(
            "⚠ Dark outdated (settings changed), collect again")
        self.lbl_dark_status.setStyleSheet("color: #e67e22")
        log.warning("Acquisition settings changed: dark spectrum cleared")

    def _collect_dark(self):
        if not self.hw.spec:
            QMessageBox.warning(
                self, "Warning", "Spectrometer not connected")
            return
        try:
            self.hw.spec.collect_dark()
            self._dark_settings = self._current_settings()
            self.lbl_dark_status.setText("✓ Dark spectrum stored")
            self.lbl_dark_status.setStyleSheet("color: green")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _clear_dark(self):
        if self.hw.spec:
            self.hw.spec.clear_dark()
        self._dark_settings = None
        self.lbl_dark_status.setText("No dark spectrum")
        self.lbl_dark_status.setStyleSheet("")

    def _preview_spectrum(self):
        if not self.hw.spec:
            QMessageBox.warning(
                self, "Warning", "Spectrometer not connected")
            return
        try:
            wl, _raw, corr = self.hw.spec.acquire(
                subtract_dark=self.chk_dark.isChecked())
            self.sig_plot.emit(None, wl, corr)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))