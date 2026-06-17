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
        self.spn_inttime.setRange(1, 60000)
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
    def apply_settings(self):
        if not self.hw.spec:
            return
        try:
            actual_integration_time = self.hw.spec.set_integration_time(
                self.spn_inttime.value())

            self.spn_inttime.blockSignals(True)
            self.spn_inttime.setValue(actual_integration_time)
            self.spn_inttime.blockSignals(False)

            self.hw.spec.set_scans_to_average(self.spn_avg.value())
            self.hw.spec.set_boxcar_width(self.spn_boxcar.value())

        except ValueError as e:
            QMessageBox.warning(
                self, "Integration Time Out of Range", str(e))
            self.spn_inttime.blockSignals(True)
            self.spn_inttime.setValue(self.hw.spec.integration_time_ms)
            self.spn_inttime.blockSignals(False)

        except Exception as e:
            QMessageBox.critical(self, "Spectrometer Error", str(e))

    # ── Private ───────────────────────────────────────────────────────
    def _collect_dark(self):
        if not self.hw.spec:
            QMessageBox.warning(
                self, "Warning", "Spectrometer not connected")
            return
        try:
            self.hw.spec.collect_dark()
            self.lbl_dark_status.setText("✓ Dark spectrum stored")
            self.lbl_dark_status.setStyleSheet("color: green")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _clear_dark(self):
        if self.hw.spec:
            self.hw.spec.clear_dark()
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