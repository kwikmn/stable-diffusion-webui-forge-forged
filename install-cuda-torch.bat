@echo off
cd /d "%~dp0"

REM ─ use your portable Python
set PYTHON=%cd%\system\python\python.exe

echo.
echo Uninstalling old torch, torchvision and torchaudio…
"%PYTHON%" -m pip uninstall -y torch torchvision torchaudio

echo.
echo Installing nightly cu128 builds of torch, torchvision and torchaudio…
"%PYTHON%" -m pip install --upgrade --pre torch torchvision torchaudio ^
    --index-url https://download.pytorch.org/whl/nightly/cu128

echo.
echo Installation complete. Verifying:
"%PYTHON%" -c "import torch; print(torch.__version__, torch.version.cuda)"
pause
