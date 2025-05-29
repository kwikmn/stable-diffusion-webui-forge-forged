@echo off

REM Ensure our portable Python + paths are set
call environment.bat

REM Try a simple pull in this folder
git -C "%~dp0" pull 2>NUL
if %ERRORLEVEL% == 0 goto :done

REM If pull failed (e.g. local changes), reset and pull again
git -C "%~dp0" reset --hard
git -C "%~dp0" pull

:done
pause
