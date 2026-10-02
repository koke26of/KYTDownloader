@echo off
cd /d "%~dp0"
python -m venv .venv || goto :error
.venv\Scripts\python -m pip install --upgrade pip

where nvidia-smi >nul 2>&1
if %errorlevel%==0 (
    echo GPU NVIDIA detectada: instalando torch con CUDA...
    .venv\Scripts\pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126 || goto :error
) else (
    echo Sin GPU NVIDIA: instalando torch para CPU...
    .venv\Scripts\pip install torch torchaudio || goto :error
)
.venv\Scripts\pip install -r requirements.txt || goto :error
echo.
echo Listo. Ejecuta run.bat para abrir la app.
pause
exit /b 0

:error
echo Fallo la instalacion.
pause
exit /b 1
