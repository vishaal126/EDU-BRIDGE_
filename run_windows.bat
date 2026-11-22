@echo off
cd /d %~dp0
if not exist .venv py -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
start "" http://localhost:8000
python app.py
pause
