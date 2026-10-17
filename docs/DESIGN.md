# Goniometer software: design decisions

Living document, filled in during the design interview. Each section covers one
showstopper from the repo review, in fix order. Status: `open` / `decided` / `done`.

Base branch: `home-branch` (16 commits ahead of `main` at 6f4d965). The first
review was done against `main`; sections below are rechecked against
`home-branch`. Changes there that matter here:
- Keysight B2900 driver added (`hardware/keysight_sourcemeter.py`).
- Saving moved from `ScanWorker._save` to `data_worker.py` (stacked format,
  still written only at the end of the scan).
- `gui/hw_imports.py` imports real hardware by default.
- `plotseparate.py` deleted.

## 1. Angle reference (second scan is offset) — done (50cd232, 30adca4)

Problem: `ScanWorker` moves to the start angle with a relative move. The Arduino
has no absolute reference and loses its zero on reset, so scan N+1 starts from
wherever scan N ended and every angle label is shifted.

Decisions:
- No physical reference: zero is set by hand (jog to 0 deg, press "Set Zero").
- Scan start/end are absolute angles from that zero. The scan drives to the
  absolute start angle, not "start angle from here".
- The app tracks a `zero_valid` flag. It is false after every connect (the
  Arduino resets on serial open). Start Scan is disabled until the user sets or
  confirms zero.
- After a scan ends or is stopped the stage stays where it is. The next scan
  drives to its own absolute start angle.

## 2. Step rounding drift — done (50cd232; actual-angle column with item 3)

Problem: each relative move is rounded to whole steps on its own (2.22 steps/deg,
5 deg = 11.1 -> 11 steps), so error accumulates (~1.6 deg over 37 points).

Decisions:
- Absolute position lives on the Arduino (AccelStepper `currentPosition`). Add a
  `MOVETO <motor> <steps>` command (firmware reflash needed). Python converts
  angle -> absolute steps once, so rounding never accumulates.
- steps/deg is computed from `steps_per_revolution` x `microstep_divisor`
  (800 x 1 today, correct for the current build) and stays configurable per
  setup. The stale `steps_per_degree` key in config.yaml is unused and gets
  removed.
- One step is 0.45 deg, so nominal angles are not hit exactly. The data file
  records the actual angle (steps read back from the Arduino / steps_per_deg)
  and keeps the nominal angle in a second column.

## 3. Partial data lost on stop/error — done (7ff0192)

Decisions:
- Append to disk per angle (spectrum and source-meter row written as soon as
  they are measured), so an abort keeps everything up to that point. The file
  layout changes from stacked raw/corrected blocks to per-angle rows.
- On a scan error (VISA timeout, compliance failure): abort, turn output off,
  keep the partial file, show the error. No skip or retry.
- The Plot tab keeps loading old stacked-format files (detect format on load).
- Implementation goes in `data_worker.py` (home-branch), not `ScanWorker`.

## 4. STOP during moves / serial thread safety — done (c20deff, 0a73715, 40ca270)

Decisions:
- STOP decelerates along the acceleration profile (AccelStepper `stop()`), so
  steps are not lost and the zero stays valid.
- Serial: a mutex around each command/reply pair. STOP is written without
  waiting for a reply; the in-flight move's own OK/ERR resolves it. Manual
  moves move off the GUI thread so the STOP button stays usable.
- Move timeout is a fixed, longer value from config (not computed per move).
- Scan Stop aborts promptly: decelerate motor, output off immediately, skip
  further acquisition, let the call in flight return before finishing.
- Also in scope here: `_start_scan` refuses to start while a worker is alive,
  and Start stays disabled until the worker thread has actually exited.

## 7. Dark spectrum invalidation — done (696eaf4)

Decisions:
- The dark stores the integration time, averages and boxcar it was taken with.
  Changing any of them clears it, and the Spectrometer tab shows "dark outdated".
  The scan refuses to subtract a stale dark.
- No software enforcement that the source is off or the sample unlit during
  dark collection. That stays with the operator.

## 8. Integration-time validation — done (16f2a2e)

Decisions:
- Minimum integration time is 3 ms (was hardcoded at 100 ms). It goes in
  config.yaml instead of being hardcoded in `hardware/spectrometer.py`.
- The spinbox applies on editing finished (Enter or focus-out), with keyboard
  tracking off. Reported bug: clearing the leading digit (field reads 00.0)
  popped the "too low" error mid-edit.
- Validate before storing: a rejected value must not change
  `integration_time_ms`; the spinbox reverts to the last valid value.
- A rejected value at scan start must abort the scan, not continue silently.

## 6. Source meter (Keithley 2461 / Keysight B2900) — done (d4d9059, d48843c, b2889e4)

Findings on `home-branch`:
- The Keithley driver never checks `*IDN?`. Connect tries it first, so with
  the Keysight's address it "connects" to the B2900 and sends
  Keithley-only commands (`:SOUR:VOLT:ILIM`, `:OUTP:SMOD HIMP`). The
  instrument rejects them, the errors are only logged as warnings, and the
  current limit is never set. The Keysight driver is never reached.
- With the default (Keithley) address in the field, the Keithley resolver
  falls back to opening every VISA resource with `*IDN?`, including the
  Arduino's serial port, which resets it and loses the zero. The Keysight
  driver is then given the same wrong address and fails too.
- If both drivers fail, `hw.source` is left pointing at a half-built object,
  so "not connected" checks pass.
- `KeysightSourceMeter`:
  - `set_voltage` forces VOLT mode, so CURR mode can't be used (the Source
    tab calls `set_source_mode` then `set_voltage`).
  - `set_current_limit` always writes the VOLT-mode compliance.
  - `self.voltage` / `self.current_limit` are never updated, so the saved
    file headers show the connect-time defaults.
  - `output_on` ignores `settle_ms` and `verify_on_output_on`: no wait before
    the spectrum, no open/short check. NPLC is never applied.
  - `disconnect` doesn't turn the output off.
- `ScanWorker` still calls the private `_query` and decodes
  `:STAT:QUES:COND?` with Keithley bit masks; the meaning on the B2900 is
  unverified.

Decisions:
- Hardware-agnostic goal: any instrument is supported by subclassing the base
  class; nothing in the GUI or `ScanWorker` names a specific model.
- Auto-detect by `*IDN?`. Each source-meter driver declares an `IDN_MATCH`
  string (Keithley "2461", Keysight "B29") and is listed in one registry. On
  connect: list VISA resources, skip serial (`ASRL...`) ports so the Arduino is
  never opened, query `*IDN?` on the rest, use the first one a registered
  driver matches. The Connect tab shows the model and driver found.
- Config overrides, both default to auto: `sourcemeter.resource` (try only
  this address) and `sourcemeter.driver` (skip detection).
- Each driver checks `*IDN?` itself in `connect()` and refuses a model it
  doesn't match.
- A failed connect leaves `hw.source = None`.
- CURR mode stays and must work on the Keysight (`set_voltage` must not force
  VOLT mode), but gets no extra polish.
- Settle wait plus open/short/compliance verification after Output ON is the
  same for every driver and lives in the base class. Drivers supply the
  instrument-specific parts (measure V, measure I, hardware compliance flag).
- `ScanWorker` uses only public base-class methods (no `_query`).

## Out of scope for now

- Showstopper 5 (mock default): done (7ec7a94). `--mock` or `GONIO_MOCK=1`
  selects the mock.

## Needs checking on hardware

None of the above has run on the real setup yet.
- Reflash the Arduino (MOVETO, new STOP behaviour).
- STOP during a long manual move and during a scan: motor decelerates,
  position afterwards matches the stage, window stays responsive.
- Stopped scan: Start returns only after the worker exits; partial files end
  with `# Ended: stopped by user`.
- USB2000+ accepts 3 ms integration time.
- Keysight B2900 commands not yet tried: `:SENS1:VOLT:PROT:TRIP?` (CURR-mode
  compliance), `:SENS1:CURR:NPLC`, `:SENS1:VOLT:NPLC`.
- Source-meter auto-detect finds the instrument and never touches the
  Arduino's serial port.
- Local `config.yaml` files: `sourcemeter.visa_resource` is renamed to
  `sourcemeter.resource`.

## Open questions

- (none)
