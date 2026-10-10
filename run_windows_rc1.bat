@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements-qt.txt
if errorlevel 1 exit /b 1
python cropwater_rs_qt.py
