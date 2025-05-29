@echo off
cd /d "%~dp0"

REM ──────────────────────────────────────────────────────────────────────
REM 1) If portable runtime is missing, fetch and unpack the split 7z parts
REM ──────────────────────────────────────────────────────────────────────
if not exist "system\python\python.exe" (
  echo Downloading split archive parts…
  for %%f in (system.7z.001 system.7z.002) do (
    powershell -Command "Invoke-WebRequest -Uri https://github.com/kwikmn/stable-diffusion-webui-forge-forged/releases/download/pre-packaged/%%f -OutFile %%f"
  )

  echo Reassembling archive…
  copy /b system.7z.001+system.7z.002 system.7z

  echo Extracting…
  "C:\Program Files\7-Zip\7z.exe" x system.7z -o"."

  echo Cleaning up…
  del system.7z.*
)
echo.

REM ──────────────────────────────────────────────────────────────────────
REM 2) Disable Forge’s built-in venv logic
REM ──────────────────────────────────────────────────────────────────────
set SKIP_VENV=1

REM ──────────────────────────────────────────────────────────────────────
REM 3) Repo-relative transformers cache
REM ──────────────────────────────────────────────────────────────────────
set TRANSFORMERS_CACHE=%cd%\transformers-cache

REM ──────────────────────────────────────────────────────────────────────
REM 4) Point at your bundled Python
REM ──────────────────────────────────────────────────────────────────────
set PYTHON=%cd%\system\python\python.exe

REM ──────────────────────────────────────────────────────────────────────
REM 5) Ensure pip & friends are on the PATH
REM ──────────────────────────────────────────────────────────────────────
set PATH=%cd%\system\python\;%cd%\system\python\Scripts\;%PATH%

REM ──────────────────────────────────────────────────────────────────────
REM 6) Custom scripts live here
REM ──────────────────────────────────────────────────────────────────────
set PYTHONPATH=%cd%\scripts;%PYTHONPATH%

echo.
echo  TRANSFORMERS_CACHE = %TRANSFORMERS_CACHE%
echo  PYTHON            = %PYTHON%
echo  PYTHONPATH        = %PYTHONPATH%
echo.

REM ──────────────────────────────────────────────────────────────────────
REM 7) Check for the right CUDA-12.8 build; install if missing
REM ──────────────────────────────────────────────────────────────────────
"%PYTHON%" -c "import torch,sys; sys.exit(0 if hasattr(torch.version,'cuda') and torch.version.cuda.startswith('12.8') else 1)"
if errorlevel 1 (
  echo Wrong or missing CUDA-12.8 torch build – running installer…
  call "%cd%\install-cuda-torch.bat"
) else (
  echo Correct CUDA-12.8 build detected – skipping reinstall.
)

echo.
