# goniometer-soft-2
Python-based GUI software for a motorized angle-resolved EL spectrum analyzer setup.



# Spectroscopy Angle Scanner


Automated goniometer control software for angle-resolved spectroscopy measurements.
Coordinates a motor controller, spectrometer, and source meter to sweep through
angular positions, collecting spectra and electrical measurements at each step.


Built with PyQt5 for the GUI, with a modular hardware abstraction layer that
supports both real instruments and mock replacements for development and testing.


---


## Project Structure


goniometer-soft-2/
├── config.yaml              # All instrument and scan settings
├── run.py                   # Optional convenience launcher
├── scan_worker.py           # Background thread that runs the scan loop
├── hardware_mock.py         # Mock instrument classes for offline testing
│
├── hardware/                # Hardware abstraction layer
│   ├── init.py          # Re-exports: MotorController, Spectrometer, SourceMeter, SourceMeterError
│   ├── _base.py             # Abstract base classes (ABCs) for all instrument categories
│   ├── _visa.py             # Shared NI-VISA resource manager loader
│   ├── motor.py             # Arduino-based motor controller (serial)
│   ├── spectrometer.py      # OceanOptics spectrometer (seabreeze)
│   └── sourcemeter.py       # Keithley 2461 source meter (VISA/SCPI)
│
└── gui/                     # PyQt5 GUI package
├── init.py           # Re-exports: MainWindow, load_config
├── main.py           # Entry point for python -m gui
├── main_window.py        # Main window — owns tabs, plots, scan lifecycle
├── state.py              # HardwareState — shared mutable container
├── bridge.py             # ScanBridge — worker thread → GUI Qt signals
├── hw_imports.py         # Single place to swap real/mock hardware
├── util.py               # Config loader
├── tabs/
│   ├── init.py
│   ├── connect_tab.py    # Instrument connection management
│   ├── spectrometer_tab.py  # Acquisition settings, dark spectrum, preview
│   ├── source_tab.py     # Source meter config, output control, verification
│   ├── scan_tab.py       # Angle scan parameters, file settings, start/stop
│   └── manual_tab.py     # Manual motor jog, position readout, single acquisition
└── widgets/
├── init.py
├── plot_panel.py     # Matplotlib spectrum plot (right panel)
└── log_panel.py      # Read-only log text box + logging handler



---


## Hardware


| Instrument           | Connection | Driver / Library                          |
|----------------------|------------|-------------------------------------------|
| Motor controller     | USB serial | Arduino (custom firmware), `pyserial`     |
| OceanOptics USB2000+ | USB        | [`seabreeze`](https://github.com/ap--/python-seabreeze) |
| Keithley 2461        | USB (TMC)  | [NI-VISA](https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html), `pyvisa` |


### Arduino Firmware Protocol


The motor controller Arduino expects a simple line-based serial protocol:


| Command                       | Response   | Description                        |
|-------------------------------|------------|------------------------------------|
| `PING`                        | `PONG`     | Connectivity check                 |
| `SPEED &lt;steps_per_sec&gt;`       | `OK`       | Set motor speed                    |
| `MOVE &lt;motor&gt; &lt;steps&gt; &lt;dir&gt;`  | `OK`       | Move motor (1 or 2), dir = 0 or 1 |
| `STOP`                        | `OK`       | Emergency stop                     |
| `ZERO`                        | `OK`       | Set current position as zero       |
| `HOME`                        | `OK`       | Return to zero position            |
| `STATUS`                      | `POS &lt;p1&gt; &lt;p2&gt;` | Query step positions          |


On connection, the Arduino resets and sends `READY` after ~2 seconds.


---


## Requirements


### System Drivers


- **NI-VISA** — required for Keithley communication.
  [Download from NI](https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html).


### Python Dependencies
PyQt5
numpy
matplotlib
pyvisa
pyserial
seabreeze
pyyaml
Install with:


bash
pip install PyQt5 numpy matplotlib pyvisa pyserial seabreeze pyyaml
___


## Configuration
All settings live in config.yaml. Example structure:


# ─────────────────────────────────────────────
#  Hardware Configuration
# ─────────────────────────────────────────────


motors:
  steps_per_revolution: 200        # native full steps per rev
  microstep_divisor: 1            # match your driver DIP settings (1/16)
  steps_per_degree: 0.555          # auto-calculated at runtime too
  max_speed_steps_per_sec: 100    # pulse rate cap
  step_pulse_us: 50                # step pulse width in microseconds (sent to Arduino)
  direction:
    motor1_invert: false           # flip if motor runs backwards
    motor2_invert: false


  # Arduino serial port
  port: "COM7"                     # Windows: COMx  |  Linux: /dev/ttyUSBx
  baud: 115200
  timeout_s: 10


spectrometer:
  model_hint: "USB2000+"           # informational only; seabreeze auto-detects
  default_integration_time_ms: 100 # absolute minimum allowed for USB2000+ spectrometer
  default_scans_to_average: 3      
  default_boxcar_width: 2          # not typically needed
  wavelength_min_nm: 200           # crop range for saved data
  wavelength_max_nm: 1100


sourcemeter:
  visa_resource: "USB0::0x05E6::0x2461::04491463::0::INSTR"  # replace serial // this is legacy since NI-VISA handles the connection automatically
  default_voltage_v: 5.0
  default_current_limit_a: 0.1
  source_mode: "VOLT"              # VOLT or CURR
  settle_time_ms: 200              # wait after output ON before collecting spectrum (milliseconds)
  nplc: 1.0                        # integration time in power-line cycles


# ─────────────────────────────────────────────
#  Scan Defaults (overridden by GUI)
# ─────────────────────────────────────────────
scan:
  angle_start_deg: -90
  angle_end_deg: 90.0
  angle_step_deg: 5.0


# ─────────────────────────────────────────────
#  Data / Logging
# ─────────────────────────────────────────────
data:
  default_filename: "scan_data"
  default_save_dir: "./data"
  timestamp_in_filename: true
  delimiter: ";"
  write_raw_counts: true
  write_dark_corrected: true


___


## Running
From the project root directory:


bash
python -m gui
Or using the convenience launcher:


python launcher.py


## Mock / Testing Mode
For development without physical hardware, the mock backend is selected in
gui/hw_imports.py:


python
# ── Real hardware ──────────────────────────────────────────────────
# from hardware import MotorController, Spectrometer, SourceMeter, SourceMeterError


# ── Mock hardware for testing ──────────────────────────────────────
from hardware_mock import MotorController, Spectrometer, SourceMeter, SourceMeterError


Swap the commented lines to switch between real and mock instruments. No other
files need to change.


Mock classes should subclass the abstract base classes in hardware/_base.py
to ensure interface compatibility:


python
from hardware._base import BaseMotorController


class MotorController(BaseMotorController):
    def connect(self):        ...
    def disconnect(self):     ...
    # ... all abstract methods must be implemented


This guarantees that if a new method is added to the base class and not
implemented in the mock, a TypeError is raised at instantiation rather than
failing silently at runtime.


## Architecture
Hardware Layer (hardware/)
Each instrument type has:


An abstract base class in _base.py defining the public interface
A concrete implementation in its own module (motor.py, spectrometer.py, sourcemeter.py)
All existing consumer code imports from the package root:


python
from hardware import MotorController, Spectrometer, SourceMeter, SourceMeterError


This import path is preserved by hardware/__init__.py re-exporting everything.


## GUI Layer (gui/)
Component   Role
HardwareState   Single mutable container holding connected instrument objects. Passed to every tab — when hardware is connected on the Connect tab, all other tabs see it immediately.
ScanBridge  Qt signal bridge. The ScanWorker runs in a background thread and calls plain Python callbacks; those callbacks emit Qt signals so the GUI thread can safely update widgets.
Tabs    Self-contained QWidget subclasses. Each tab owns its own UI and handlers. Cross-tab communication goes through signals or the shared HardwareState.
PlotPanel   Matplotlib canvas widget. Tabs that need to plot emit a sig_plot signal; MainWindow wires it to PlotPanel.plot_spectrum.
MainWindow  Coordinator. Owns the tab bar, right panel, progress bar, and scan lifecycle. Does not contain instrument-specific UI code.
Extending
Adding a new instrument:


Add a new ABC method set to hardware/_base.py (if it's a new category)
Create the implementation in hardware/your_instrument.py
Re-export from hardware/__init__.py
Add a mock in hardware_mock.py subclassing the ABC
Adding a new GUI tab:


Create gui/tabs/your_tab.py with a QWidget subclass
Accept hw (HardwareState) and cfg in the constructor
Register it in MainWindow._build_ui():
python
self.tab_yours = YourTab(self.hw, self.cfg)
self.tabs.addTab(self.tab_yours, "Your Tab")
Wire any signals in MainWindow._connect_signals()
Adding a new plot type:


Add a method to PlotPanel (e.g. plot_heatmap)
Or create a new widget class in gui/widgets/ and add it to the right panel layout


## Source Meter Verification
The Keithley 2461 wrapper includes automatic output verification when
verify_on_output_on is enabled. After turning the output on, it checks:


Check   VOLT mode   CURR mode
Signal present  Measured current ≥ current_threshold    Measured voltage ≥ voltage_threshold
No compliance   Measured current &lt; compliance_fraction × current limit  Measured voltage &lt; compliance_fraction × voltage limit
Both checks also read the instrument's hardware compliance status register.
If either check fails, a SourceMeterError is raised and the GUI
automatically disables the output.


These thresholds are configurable both in config.yaml and from the
Source tab's Verification Settings panel at runtime.