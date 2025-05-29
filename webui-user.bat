@echo off

if not defined PYTHON           set PYTHON=
if not defined GIT              set GIT=
if not defined VENV_DIR         set VENV_DIR=
if not defined COMMANDLINE_ARGS set COMMANDLINE_ARGS=--cuda-malloc --opt-sdp-attention --opt-split-attention --opt-channelslast --precision autocast

REM point at your existing Forge2 install
set Forge_HOME=R:\Forge2\webui

REM redirect only SD checkpoints, embeddings, LoRAs, and ControlNet preprocessor models
set COMMANDLINE_ARGS=%COMMANDLINE_ARGS% ^
  --ckpt-dir "%Forge_HOME%\models\Stable-diffusion" ^
  --embeddings-dir "%Forge_HOME%\embeddings" ^
  --lora-dir "%Forge_HOME%\models\Lora" ^
  --controlnet-preprocessor-models-dir "%Forge_HOME%\models\ControlNetPreprocessor"

call webui.bat
