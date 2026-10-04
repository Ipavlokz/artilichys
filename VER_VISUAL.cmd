@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Primero prepara el programa con PROBAR_EEG.cmd o GUIA_WINDOWS.md.
    pause
    exit /b 1
)
set "NEUROVISUAL_VIEWER_SESSION=sessions\ensayo-visual-%RANDOM%-%RANDOM%"
echo Preparando dos reglas artisticas con la misma grabacion REAL de OpenBCI.
echo El Unicorn no es necesario. Este ensayo usa una grabacion guardada.
".venv\Scripts\python.exe" -m neurovisual replay examples/recordings/openbci --speed 0 --no-osc --quiet --record "%NEUROVISUAL_VIEWER_SESSION%\original"
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m neurovisual replay examples/recordings/openbci --config examples/visual-custom.json --speed 0 --no-osc --quiet --record "%NEUROVISUAL_VIEWER_SESSION%\alternativa"
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m neurovisual view "%NEUROVISUAL_VIEWER_SESSION%\original" --compare "%NEUROVISUAL_VIEWER_SESSION%\alternativa" --output "%NEUROVISUAL_VIEWER_SESSION%\viewer.html" --open
if errorlevel 1 goto error
echo.
echo Visor preparado en: %NEUROVISUAL_VIEWER_SESSION%\viewer.html
echo Pulsa Reproducir en el navegador. Puedes volver a abrir el HTML con doble clic.
pause
exit /b 0
:error
echo No se pudo preparar el visor. Revisa el mensaje anterior y GUIA_WINDOWS.md.
pause
exit /b 1
