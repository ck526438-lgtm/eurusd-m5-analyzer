@echo off
REM Lance la surveillance EURUSD M5 (garde MetaTrader 5 ouvert et connecte)
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv
    call .venv\Scripts\activate
    pip install -r requirements.txt MetaTrader5 plyer
) else (
    call .venv\Scripts\activate
)
python main.py live
pause
