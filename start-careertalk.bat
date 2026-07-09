@echo off
chcp 65001 >nul
cd /d "%~dp0careertalk"
python server.py --mock --port 8001
