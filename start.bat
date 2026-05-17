@echo off
chcp 65001 >nul
cd /d %~dp0
echo ================================================
echo   说明书保管箱启动中...
echo   首次使用请先在 config.json 中填入 ANTHROPIC_API_KEY
echo ================================================
start "" http://127.0.0.1:8765
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
pause
