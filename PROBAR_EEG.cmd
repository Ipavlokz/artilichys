@echo off
setlocal
cd /d "%~dp0"
echo Preparando Neurovisual. La primera vez se descargan las dependencias de Python.
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto error
set "NEUROVISUAL_DEMO_SESSION=sessions\grabacion-real-%RANDOM%-%RANDOM%"
echo.
echo Reproduciendo una grabacion REAL de OpenBCI de unos 60 segundos.
echo El Unicorn no es necesario para esta prueba.
echo Resultados en: %NEUROVISUAL_DEMO_SESSION%
echo.
".venv\Scripts\python.exe" -m neurovisual replay examples/recordings/openbci --display text --record "%NEUROVISUAL_DEMO_SESSION%"
if errorlevel 1 goto error
echo.
echo Prueba terminada. Los resultados estan guardados en %NEUROVISUAL_DEMO_SESSION%
pause
exit /b 0

:error
echo.
echo No se pudo completar la prueba. Revisa el mensaje anterior.
echo Consulta GUIA_WINDOWS.md; comprueba que Python esta instalado y hay Internet para instalar dependencias.
pause
exit /b 1
