"""
Plot tab — file-management controls (left panel) and multi-plot
analysis canvas (right panel) for viewing saved scan data.
"""

import os
import re
import logging

import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QFileDialog, QCheckBox,
    QComboBox, QMessageBox, QSizePolicy, QSpacerItem,
    QDoubleSpinBox, QFormLayout,
)
from PyQt5.QtCore import pyqtSignal

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure

from gui.plot_style import (
    OI, MAP_CMAP, MM, DOUBLE, SCREEN_SCALE,
    nature_rc, panel_labels, style_colorbar,
)

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Data loader
# ═══════════════════════════════════════════════════════════════════

def load_scan_file(path: str, sourcemeter_path: str = None) -> dict:
    """
    Load spectrum + sourcemeter files produced by ``_save()``.

    Returns dict with keys:
        meta, wl, ang, v, i, comp, raw, corr, path
    """
    # ── Auto-detect sourcemeter path ──────────────────────────────
    if sourcemeter_path is None:
        base, ext = os.path.splitext(path)
        m = re.match(r'^(.+?)_(\d{8}_\d{6})$', base)
        if m:
            candidate = f"{m.group(1)}_sourcemeter_{m.group(2)}{ext}"
        else:
            candidate = f"{base}_sourcemeter{ext}"
        if os.path.isfile(candidate):
            sourcemeter_path = candidate

    # ── Spectrum file ─────────────────────────────────────────────
    with open(path) as f:
        lines = f.read().splitlines()

    meta, data_lines = {}, []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith('#'):
            content = s[1:].strip()
            if ':' in content:
                k, v = content.split(':', 1)
                meta[k.strip()] = v.strip()
            continue
        data_lines.append(s)

    if not data_lines:
        raise ValueError(f"No data lines in {path}")

    # Detect delimiter
    first = data_lines[0]
    delimiter = '\t'
    for d in [';', '\t', ',']:
        if d in first:
            delimiter = d
            break

    wl_parts = first.split(delimiter)
    wl = np.array([float(x) for x in wl_parts[1:]])
    n = len(wl)

    body = data_lines[1:]
    n_angles = len(body) // 2
    if n_angles == 0 or len(body) != 2 * n_angles:
        raise ValueError(
            f"Expected even number of data rows, got {len(body)}")

    def _parse_block(block):
        angles, values = [], []
        for row in block:
            parts = row.split(delimiter)
            angles.append(float(parts[0]))
            values.append([float(x) for x in parts[1:1 + n]])
        return np.array(angles), np.array(values)

    ang, raw = _parse_block(body[:n_angles])
    _, corr  = _parse_block(body[n_angles:])

    # ── Sourcemeter file ──────────────────────────────────────────
    volt = np.zeros(n_angles)
    curr = np.zeros(n_angles)
    comp = np.zeros(n_angles, dtype=bool)

    if sourcemeter_path and os.path.isfile(sourcemeter_path):
        with open(sourcemeter_path) as f:
            src_lines = f.read().splitlines()

        src_delim = delimiter
        for sl in src_lines:
            ss = sl.strip()
            if ss and not ss.startswith('#'):
                for d in [';', '\t', ',']:
                    if d in ss:
                        src_delim = d
                        break
                break

        idx = 0
        for line in src_lines:
            ss = line.strip()
            if not ss or ss.startswith('#'):
                continue
            try:
                float(ss.split(src_delim)[0])
            except ValueError:
                continue
            parts = ss.split(src_delim)
            if idx < n_angles:
                volt[idx] = float(parts[1])
                curr[idx] = float(parts[2])
                comp[idx] = bool(int(float(parts[3])))
                idx += 1

    return dict(meta=meta, wl=wl, ang=ang, v=volt, i=curr,
                comp=comp, raw=raw, corr=corr, path=path)


# ═══════════════════════════════════════════════════════════════════
#  Figure  (shared by the on-screen canvas and the export)
# ═══════════════════════════════════════════════════════════════════

def _trapz(y, x, axis=-1):
    f = getattr(np, "trapezoid", None) or np.trapz
    return f(y, x, axis=axis)


def draw_analysis(fig, d: dict, show_raw: bool = False,
                  normal_angle: float = 0.0, scale: float = 1.0):
    """
    Draw the scan analysis into *fig* (call inside
    ``matplotlib.rc_context(nature_rc(scale))``):

    a  angle–wavelength intensity map (angle on x)
    b  integrated intensity vs angle with the Lambertian reference
    c  the same, normalised at the surface normal, on a polar plot
    """
    o = np.argsort(d['ang'], kind='stable')
    ang  = d['ang'][o]
    wl   = d['wl']
    sp   = (d['raw'] if show_raw else d['corr'])[o]
    comp = d['comp'][o]
    label = 'Raw' if show_raw else 'Dark-corrected'

    I = _trapz(sp, wl, axis=1)
    j0 = int(np.argmin(np.abs(ang - normal_angle)))
    I0 = I[j0] if I[j0] > 0 else np.nanmax(I)
    if not I0 > 0:
        I0 = 1.0
    In = I / I0

    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.1],
                          width_ratios=[1.25, 1])
    ax_m = fig.add_subplot(gs[0, :])
    ax_i = fig.add_subplot(gs[1, 0])
    ax_p = fig.add_subplot(gs[1, 1], projection='polar')

    comp_kw = dict(marker='x', color=OI['vermillion'], s=14 * scale**2,
                   lw=0.7 * scale, zorder=5, label='In compliance')

    # ── a  Heatmap: angle on x, wavelength on y ──────────────────
    im = ax_m.pcolormesh(ang, wl, sp.T, shading='nearest',
                         cmap=MAP_CMAP, rasterized=True)
    ax_m.set(xlabel='Angle (°)', ylabel='Wavelength (nm)')
    for s_ in ax_m.spines.values():
        s_.set_visible(True)
    cb = fig.colorbar(im, ax=ax_m, pad=0.02, aspect=30)
    style_colorbar(cb, f'{label} intensity (counts)', scale)

    # ── b  Linear angular dispersion ─────────────────────────────
    ax_i.plot(ang, I, 'o-', color=OI['blue'], label='Measured')
    if len(ang) > 1:
        tt = np.linspace(ang.min(), ang.max(), 361)
        lam = I0 * np.clip(np.cos(np.deg2rad(tt - normal_angle)), 0, None)
        ax_i.plot(tt, lam, '--', color=OI['black'], lw=0.6 * scale,
                  label='Lambertian')
    if comp.any():
        ax_i.scatter(ang[comp], I[comp], **comp_kw)
    ax_i.set(xlabel='Angle (°)',
             ylabel='Integrated intensity (counts nm)')
    ax_i.legend(loc='best')

    # ── c  Polar angular dispersion ──────────────────────────────
    th = np.deg2rad(ang - normal_angle)
    ax_p.plot(th, In, 'o-', color=OI['blue'])
    if len(th) > 1:
        tt = np.linspace(th.min(), th.max(), 361)
        ax_p.plot(tt, np.clip(np.cos(tt), 0, None), '--',
                  color=OI['black'], lw=0.6 * scale)
    if comp.any():
        ax_p.scatter(th[comp], In[comp], **comp_kw)
    ax_p.set_theta_zero_location('N')
    ax_p.set_theta_direction(-1)
    span = np.rad2deg(th.max() - th.min())
    if 1 < span <= 360:
        ax_p.set_thetamin(np.rad2deg(th.min()))
        ax_p.set_thetamax(np.rad2deg(th.max()))
    rmax = np.nanmax(In) if np.isfinite(In).any() else 1.0
    ax_p.set_rlim(0, max(1.05, rmax * 1.05))
    ax_p.grid(lw=0.3 * scale, alpha=0.6)
    ax_p.spines['polar'].set_linewidth(0.5 * scale)
    ax_p.tick_params(pad=1 * scale)
    ax_p.set_title('Normalized integrated intensity', pad=4 * scale)

    panel_labels([ax_m, ax_i], dx=-30, scale=scale)
    panel_labels([ax_p], start='c', dx=-4, scale=scale)
    return fig


# ═══════════════════════════════════════════════════════════════════
#  Analysis canvas  (placed on the RIGHT panel by MainWindow)
# ═══════════════════════════════════════════════════════════════════

class ScanAnalysisCanvas(QWidget):
    """
    Toolbar + matplotlib figure with the angle–wavelength map and the
    linear and polar angular-dispersion plots (see :func:`draw_analysis`).

    MainWindow places this in the right panel alongside PlotPanel
    (inside a QStackedWidget).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = None
        self._show_raw = False
        self._normal = 0.0
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.fig = Figure(layout='constrained', facecolor='white')
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toolbar = NavigationToolbar(self.canvas, self)

        lay.addWidget(self.toolbar)
        lay.addWidget(self.canvas, stretch=1)

    # ── Public API ────────────────────────────────────────────────
    def plot(self, data: dict, show_raw: bool = False):
        self._data = data
        self._show_raw = show_raw
        self._redraw()

    def set_show_raw(self, raw: bool):
        self._show_raw = raw
        self._redraw()

    def set_normal_angle(self, angle: float):
        self._normal = angle
        self._redraw()

    def clear(self):
        self._data = None
        self.fig.clear()
        self.canvas.draw_idle()

    def export(self, path: str):
        """Save the figure at Nature double-column size (183 mm wide)."""
        if self._data is None:
            raise RuntimeError("No scan loaded")
        with matplotlib.rc_context(nature_rc(1.0)):
            fig = Figure(figsize=(DOUBLE, 120 * MM), layout='constrained')
            draw_analysis(fig, self._data, self._show_raw, self._normal)
            fig.savefig(path)

    # ── Internals ─────────────────────────────────────────────────
    def _redraw(self):
        if self._data is None:
            return
        self.fig.clear()
        with matplotlib.rc_context(nature_rc(SCREEN_SCALE)):
            draw_analysis(self.fig, self._data, self._show_raw,
                          self._normal, scale=SCREEN_SCALE)
            self.fig.suptitle(os.path.basename(self._data['path']),
                              fontweight='bold')
            self.canvas.draw_idle()


# ═══════════════════════════════════════════════════════════════════
#  PlotTab  (placed on the LEFT panel as a tab — controls only)
# ═══════════════════════════════════════════════════════════════════

class PlotTab(QWidget):
    """
    Narrow control panel for loading / browsing saved scan files.

    The heavy plotting is done by ``self.analysis_canvas``
    (a :class:`ScanAnalysisCanvas`), which **MainWindow** must place
    into the right-side panel.

    Signals
    -------
    sig_show_analysis
        Emitted when the user loads a file — MainWindow should switch
        the right panel to show ``self.analysis_canvas``.
    sig_show_live
        Emitted when the user clears all files — MainWindow can
        switch back to the live PlotPanel.
    """

    sig_show_analysis = pyqtSignal()
    sig_show_live     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._datasets = {}                          # path → data dict

        # The canvas that MainWindow places on the right
        self.analysis_canvas = ScanAnalysisCanvas()

        self._build_ui()

    # ── UI (narrow — fits in 400-480 px) ──────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)

        # ── File management ───────────────────────────────────────
        file_grp = QGroupBox("Scan Files")
        file_lay = QVBoxLayout(file_grp)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("Add file(s)…")
        self.btn_add.clicked.connect(self._add_files)
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.clicked.connect(self._remove_current)
        self.btn_clear = QPushButton("Clear all")
        self.btn_clear.clicked.connect(self._clear_files)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_clear)
        file_lay.addLayout(btn_row)

        self.cmb_files = QComboBox()
        self.cmb_files.setToolTip("Select a loaded scan file to view")
        self.cmb_files.currentIndexChanged.connect(
            self._on_file_selected)
        file_lay.addWidget(self.cmb_files)

        lay.addWidget(file_grp)

        # ── Display options ───────────────────────────────────────
        opt_grp = QGroupBox("Display Options")
        opt_lay = QVBoxLayout(opt_grp)

        self.chk_raw = QCheckBox("Show raw counts (instead of corrected)")
        self.chk_raw.toggled.connect(self._on_raw_toggled)
        opt_lay.addWidget(self.chk_raw)

        form = QFormLayout()
        self.spn_normal = QDoubleSpinBox()
        self.spn_normal.setRange(-180.0, 180.0)
        self.spn_normal.setDecimals(1)
        self.spn_normal.setSingleStep(0.5)
        self.spn_normal.setSuffix(" °")
        self.spn_normal.setToolTip(
            "Goniometer angle of the surface normal: the polar plot is "
            "centred and normalised here, and the Lambertian reference "
            "is cos(θ − normal)")
        self.spn_normal.valueChanged.connect(
            self.analysis_canvas.set_normal_angle)
        form.addRow("Normal angle:", self.spn_normal)
        opt_lay.addLayout(form)

        self.btn_export = QPushButton("Export figure…")
        self.btn_export.setToolTip(
            "Save at Nature double-column size (183 mm) as PDF, PNG or SVG")
        self.btn_export.clicked.connect(self._export_figure)
        opt_lay.addWidget(self.btn_export)

        lay.addWidget(opt_grp)

        # ── Summary ──────────────────────────────────────────────
        info_grp = QGroupBox("File Summary")
        info_lay = QVBoxLayout(info_grp)

        self.lbl_info = QLabel("No file loaded")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet(
            "QLabel { padding: 4px; }")
        info_lay.addWidget(self.lbl_info)

        # Sourcemeter status
        self.lbl_sm = QLabel("")
        self.lbl_sm.setWordWrap(True)
        self.lbl_sm.setStyleSheet(
            "QLabel { color: grey; padding: 2px; }")
        info_lay.addWidget(self.lbl_sm)

        lay.addWidget(info_grp)

        # ── Metadata ─────────────────────────────────────────────
        meta_grp = QGroupBox("File Metadata")
        meta_lay = QVBoxLayout(meta_grp)

        self.lbl_meta = QLabel("")
        self.lbl_meta.setWordWrap(True)
        self.lbl_meta.setStyleSheet(
            "QLabel { font-family: monospace; font-size: 9pt; "
            "padding: 4px; }")
        meta_lay.addWidget(self.lbl_meta)

        lay.addWidget(meta_grp)

        lay.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Minimum,
                        QSizePolicy.Expanding))

    # ── File handling ─────────────────────────────────────────────
    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Spectrum Scan Files", "",
            "Scan Files (*.txt *.dat);;All Files (*)")
        if not paths:
            return

        # Skip sourcemeter companion files
        paths = [p for p in paths
                 if '_sourcemeter_' not in os.path.basename(p)]

        errors = []
        for p in paths:
            if p in self._datasets:
                continue
            try:
                data = load_scan_file(p)
                self._datasets[p] = data
                self.cmb_files.addItem(os.path.basename(p), userData=p)
                log.info("Loaded %s", os.path.basename(p))
            except Exception as e:
                errors.append(f"{os.path.basename(p)}: {e}")
                log.warning("Failed to load %s: %s",
                            os.path.basename(p), e)

        if errors:
            QMessageBox.warning(
                self, "Load Warnings",
                "Some files could not be loaded:\n\n"
                + "\n".join(errors))

        if self.cmb_files.count():
            self.cmb_files.setCurrentIndex(
                self.cmb_files.count() - 1)
            self.sig_show_analysis.emit()

    def _remove_current(self):
        idx = self.cmb_files.currentIndex()
        if idx < 0:
            return
        path = self.cmb_files.currentData()
        self._datasets.pop(path, None)
        self.cmb_files.removeItem(idx)
        if self.cmb_files.count() == 0:
            self._clear_display()
            self.sig_show_live.emit()

    def _clear_files(self):
        self._datasets.clear()
        self.cmb_files.clear()
        self._clear_display()
        self.sig_show_live.emit()

    def _clear_display(self):
        self.analysis_canvas.clear()
        self.lbl_info.setText("No file loaded")
        self.lbl_sm.clear()
        self.lbl_meta.clear()

    def _on_file_selected(self, idx):
        if idx < 0:
            return
        path = self.cmb_files.currentData()
        if path is None or path not in self._datasets:
            return
        data = self._datasets[path]
        self.analysis_canvas.plot(data, self.chk_raw.isChecked())
        self._show_summary(data)
        self.sig_show_analysis.emit()

    def _on_raw_toggled(self, checked):
        self.analysis_canvas.set_show_raw(checked)

    def _export_figure(self):
        path = self.cmb_files.currentData()
        if path is None:
            return
        default = os.path.splitext(path)[0] + "_analysis.pdf"
        out, _ = QFileDialog.getSaveFileName(
            self, "Export Figure", default,
            "PDF (*.pdf);;PNG (*.png);;SVG (*.svg)")
        if not out:
            return
        try:
            self.analysis_canvas.export(out)
            log.info("Figure saved to %s", out)
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

    # ── Programmatic API (called by MainWindow after scan) ────────
    def load_and_show(self, path: str):
        """Load a file and select it (e.g. after a scan finishes)."""
        if path not in self._datasets:
            try:
                data = load_scan_file(path)
            except Exception as e:
                log.error("Cannot load %s: %s", path, e)
                return
            self._datasets[path] = data
            self.cmb_files.addItem(os.path.basename(path),
                                   userData=path)

        idx = self.cmb_files.findData(path)
        if idx >= 0:
            self.cmb_files.setCurrentIndex(idx)
        self.sig_show_analysis.emit()

    # ── Summary display ───────────────────────────────────────────
    def _show_summary(self, data: dict):
        d = data
        ang, wl, corr = d['ang'], d['wl'], d['corr']

        flat_idx = np.argmax(corr)
        r, c = np.unravel_index(flat_idx, corr.shape)

        integrated = corr.sum(axis=1)
        best_idx = np.argmax(integrated)

        self.lbl_info.setText(
            f"<b>Angles:</b> {len(ang)}  "
            f"({ang[0]:.1f}° → {ang[-1]:.1f}°)<br>"
            f"<b>Wavelengths:</b> {len(wl)}  "
            f"({wl[0]:.1f} – {wl[-1]:.1f} nm)<br>"
            f"<b>Peak:</b> {corr[r, c]:.1f}  @  "
            f"{wl[c]:.2f} nm, {ang[r]:.1f}°<br>"
            f"<b>Best integrated angle:</b> {ang[best_idx]:.1f}°<br>"
            f"<b>Compliance:</b> {d['comp'].sum()} / {len(d['comp'])}"
        )

        has_sm = np.any(d['v'] != 0) or np.any(d['i'] != 0)
        if has_sm:
            self.lbl_sm.setText(
                f"V: {d['v'].min():.3f} – {d['v'].max():.3f} V\n"
                f"I: {d['i'].min()*1e3:.3f} – "
                f"{d['i'].max()*1e3:.3f} mA")
        else:
            self.lbl_sm.setText("No sourcemeter data found")

        # Metadata from file header
        if d['meta']:
            lines = [f"{k}: {v}" for k, v in d['meta'].items()]
            self.lbl_meta.setText("\n".join(lines))
        else:
            self.lbl_meta.setText("(none)")