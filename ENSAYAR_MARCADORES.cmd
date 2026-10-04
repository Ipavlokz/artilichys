@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Primero prepara el programa con PROBAR_EEG.cmd o GUIA_WINDOWS.md.
    pause
    exit /b 1
)
set "NEUROVISUAL_MARKER_SESSION=sessions\ensayo-marcadores-%RANDOM%-%RANDOM%"
echo Ensayo de 3 minutos con EEG SIMULADO. El programa no reproduce audio.
echo Inicia SIN musica. Abre MARCAR_MUSICA.cmd en otra ventana para anotar cambios.
echo Resultados en: %NEUROVISUAL_MARKER_SESSION%
echo.
".venv\Scripts\python.exe" -m neurovisual run --source simulated --duration 180 --manual-markers --display text --record "%NEUROVISUAL_MARKER_SESSION%"
if errorlevel 1 (
    echo No se completo el ensayo. Revisa el mensaje anterior y GUIA_WINDOWS.md.
    pause
    exit /b 1
)
echo.
echo Ensayo terminado. Informe descriptivo de datos SIMULADOS:
".venv\Scripts\python.exe" -m neurovisual compare "%NEUROVISUAL_MARKER_SESSION%" --display text --output "%NEUROVISUAL_MARKER_SESSION%\comparison.json"
pause
