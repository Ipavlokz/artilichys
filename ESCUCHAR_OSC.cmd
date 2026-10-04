@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Primero ejecuta PROBAR_EEG.cmd para preparar Python y el programa.
    pause
    exit /b 1
)
echo Deja esta ventana abierta y ejecuta PROBAR_EEG.cmd en otra ventana.
echo Aqui apareceran las instrucciones numericas recibidas por OSC.
".venv\Scripts\python.exe" -m neurovisual listen
pause
