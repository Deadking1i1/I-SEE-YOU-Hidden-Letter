@echo off
cd /d "%~dp0"
py -c "import pygame, numpy" >nul 2>&1
if errorlevel 1 py -m pip install -r requirements.txt
py main.py
if errorlevel 1 pause
