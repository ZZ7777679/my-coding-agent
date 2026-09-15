@echo off
setlocal DisableDelayedExpansion
title My Coding Agent

pushd "%~dp0" || goto location_error
set "AGENT_EXIT_CODE=1"

where node.exe >nul 2>&1
if errorlevel 1 goto missing_node
if not exist ".venv\Scripts\python.exe" goto missing_python
if not exist "apps\desktop\node_modules\electron-vite\bin\electron-vite.js" goto missing_frontend
if not exist "apps\desktop\node_modules\electron\dist\electron.exe" goto missing_electron

rem Desktop launches must not inherit an Electron-as-Node setting from a parent terminal.
set "ELECTRON_RUN_AS_NODE="
echo Starting My Coding Agent...
echo You can minimize this console. Close the app window to stop.
echo.
node.exe "scripts\dev.mjs"
set "AGENT_EXIT_CODE=%ERRORLEVEL%"
if "%AGENT_EXIT_CODE%"=="0" goto done
echo.
echo The app exited with an error. Check the messages above.
goto failed

:missing_node
echo Node.js was not found. Install the version listed in .node-version.
goto failed

:missing_python
echo The Python environment is missing. Run this in the project folder:
echo   uv sync --locked
goto failed

:missing_frontend
echo Desktop dependencies are missing. Run this in the project folder:
echo   npm.cmd --prefix apps/desktop ci
goto failed

:missing_electron
echo The Electron runtime is missing. Run this in the project folder:
echo   npm.cmd --prefix apps/desktop run install:electron
goto failed

:failed
echo.
echo See README.md for installation instructions.
pause

:done
popd
exit /b %AGENT_EXIT_CODE%

:location_error
echo Cannot open the project folder. Check its location and permissions.
pause
exit /b 1
