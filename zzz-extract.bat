@echo off
chcp 65001 >nul
python -X utf8 "%~dp0scripts\zx.py" %*
if "%~1"=="" pause
