@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Primero ejecuta PROBAR_EEG.cmd para preparar Python.
 pause
 exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\prepare_unicorn.ps1"
if errorlevel 1 (
 pause
 exit /b 1
)
echo Cierra adquisiciones de Unicorn Suite que esten usando el dispositivo.
echo Activa tu licencia Python API en Suite. No necesitas compartir la clave.
echo En TouchDesigner: OSC In CHOP, Network Port 9000, Active On.
echo Para finalizar: Ctrl+C. Se guardara la sesion en sessions.
".venv\Scripts\python.exe" -m neurovisual run --source unicorn --sdk-path "vendor\unicorn\python-api\Lib" --display text
pause
