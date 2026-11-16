@echo off
REM Build GoniometerControl.exe with PyInstaller (run on Windows).
REM Output: dist\GoniometerControl\GoniometerControl.exe  (+ config.yaml next to it)
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pyinstaller pyqt5 matplotlib numpy pyyaml pyserial pyvisa seabreeze || goto :error

python -m PyInstaller --noconfirm --clean --windowed ^
  --name GoniometerControl ^
  --collect-all seabreeze ^
  --collect-submodules pyvisa ^
  --hidden-import matplotlib.backends.backend_qt5agg ^
  --exclude-module tkinter ^
  launcher.py || goto :error

copy /y config.yaml dist\GoniometerControl\config.yaml >nul || goto :error

echo.
echo Done: dist\GoniometerControl\GoniometerControl.exe
echo Edit dist\GoniometerControl\config.yaml to change COM port etc.
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
