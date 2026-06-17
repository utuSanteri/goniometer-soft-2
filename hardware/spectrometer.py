"""
OceanOptics spectrometer via seabreeze.
"""

import logging
import numpy as np

from hardware._base import BaseSpectrometer

log = logging.getLogger(__name__)


class Spectrometer(BaseSpectrometer):
    """Wraps seabreeze for an OceanOptics device."""

    def __init__(self,
                 integration_time_ms: float = 100.0,
                 scans_to_average: int = 3,
                 boxcar_width: int = 2,
                 wl_min: float = 200.0,
                 wl_max: float = 1100.0):
        self._spec = None
        self.integration_time_ms = integration_time_ms
        self.scans_to_average = scans_to_average
        self.boxcar_width = boxcar_width
        self.wl_min = wl_min
        self.wl_max = wl_max
        self._dark = None

    # ── Connection ────────────────────────────────────────────────────
    def connect(self):
        import seabreeze.spectrometers as sb
        devices = sb.list_devices()
        if not devices:
            raise RuntimeError(
                "No OceanOptics spectrometer found.\n"
                "Check USB connection and seabreeze install.")
        self._spec = sb.Spectrometer(devices[0])
        self._spec.integration_time_micros(
            int(self.integration_time_ms * 1000))
        log.info("Spectrometer connected: %s", self._spec.model)

    def disconnect(self):
        if self._spec:
            self._spec.close()
            self._spec = None
            log.info("Spectrometer disconnected")

    def is_connected(self) -> bool:
        return self._spec is not None

    # ── Settings ──────────────────────────────────────────────────────
    def set_integration_time(self, ms: float):
        self.integration_time_ms = ms
        if self.integration_time_ms < 100:
            raise ValueError(
                f"Integration time {ms:.2f} ms is below the minimum "
                f"allowed by this device (100.00 ms).\n"
                f"Value must be at least 100 ms."
            )
        elif self._spec:
            self._spec.integration_time_micros(int(ms * 1000))

    def set_scans_to_average(self, n: int):
        self.scans_to_average = max(1, n)

    def set_boxcar_width(self, w: int):
        self.boxcar_width = max(0, w)

    # ── Dark ──────────────────────────────────────────────────────────
    def collect_dark(self):
        wl, counts = self._acquire_averaged()
        self._dark = counts.copy()
        log.info("Dark spectrum collected (%d pixels)", len(self._dark))

    def clear_dark(self):
        self._dark = None

    # ── Acquisition ───────────────────────────────────────────────────
    def _acquire_averaged(self) -> tuple:
        stacks = []
        for _ in range(self.scans_to_average):
            stacks.append(self._spec.intensities())
        counts = np.mean(stacks, axis=0)

        if self.boxcar_width > 0:
            kernel = np.ones(2 * self.boxcar_width + 1)
            kernel /= kernel.sum()
            counts = np.convolve(counts, kernel, mode='same')

        wl = self._spec.wavelengths()
        mask = (wl >= self.wl_min) & (wl <= self.wl_max)
        return wl[mask], counts[mask]

    def acquire(self, subtract_dark: bool = True) -> tuple:
        wl, raw = self._acquire_averaged()
        if subtract_dark and self._dark is not None:
            corr = raw - self._dark[:len(raw)]
        else:
            corr = raw.copy()
        return wl, raw, corr

    def has_dark(self) -> bool:
        return self._dark is not None