@echo off
setlocal
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
where py >nul 2>nul && (py -3 -m proofdesk & goto :done)
where python >nul 2>nul && (python -m proofdesk & goto :done)
echo.
echo ProofDesk needs Python, which is not installed on this computer.
echo.
echo 1. A download page will open. Click the big yellow "Download Python" button.
echo 2. Run the file you download. On the first screen, tick "Add python.exe to PATH".
echo 3. Click "Install Now", then double-click "Start ProofDesk" again.
echo.
echo (Or skip all this: download ProofDesk-Windows.zip from the Releases page instead.)
start "" https://www.python.org/downloads/
:done
pause
