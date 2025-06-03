@echo off

if not defined PYTHON           set PYTHON=
if not defined GIT              set GIT=
if not defined VENV_DIR         set VENV_DIR=
if not defined COMMANDLINE_ARGS set COMMANDLINE_ARGS=--cuda-malloc --opt-sdp-attention --opt-split-attention --opt-channelslast --precision autocast

REM point at your existing Forge2 install

REM redirect only SD checkpoints, embeddings, LoRAs, and ControlNet preprocessor models

call webui.bat
