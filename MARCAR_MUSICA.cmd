@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Primero prepara el programa con PROBAR_EEG.cmd o GUIA_WINDOWS.md.
    pause
    exit /b 1
)
:menu
echo.
echo M = marcar MUSICA. R = marcar REFERENCIA sin musica. S = salir de este menu.
echo Debe estar abierta una sesion con --manual-markers en el puerto 9001.
choice /c MRS /n /m "Elige M, R o S: "
if errorlevel 3 exit /b 0
if errorlevel 2 goto referencia
".venv\Scripts\python.exe" -m neurovisual mark music
if errorlevel 1 goto error
goto menu
:referencia
".venv\Scripts\python.exe" -m neurovisual mark reference
if errorlevel 1 goto error
goto menu
:error
echo No llego confirmacion. Revisa la ventana del ensayo y el mensaje anterior.
echo El menu no inicia ni detiene tu reproductor de musica.
pause
goto menu
