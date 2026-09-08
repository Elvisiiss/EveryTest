@echo off
chcp 65001 >nul
title 1688 Offer Monitor
cd /d "%~dp0"
..\.venv\Scripts\python.exe monitor.py
echo.
echo Program exited. Press any key to close this window ...
pause >nul
