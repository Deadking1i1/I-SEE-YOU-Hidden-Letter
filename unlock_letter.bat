@echo off
cd /d "%~dp0"
py -c "import cryptography" >nul 2>&1
if errorlevel 1 py -m pip install -r requirements-unlock.txt
if errorlevel 1 (
    echo Could not install the unlock dependency. Check Python and your internet connection, then try again.
    pause
    exit /b 1
)
py tools\read_private_letter.py
if errorlevel 1 pause
