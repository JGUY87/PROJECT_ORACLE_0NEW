@echo off
echo ==================================================
echo  Starting All PROJECT_ORACLE_0 Services
echo ==================================================
set "PYTHON_EXE=C:\Users\HP\PROJECT_ORACLE_0_NEW\trading_env\Scripts\python.exe"

echo.
echo ---> Installing/Updating required packages...
%PYTHON_EXE% -m pip install --upgrade "uvicorn[standard]" "fastapi" "streamlit" "matplotlib" "aiogram" "requests"

echo.
echo ---> Starting Main Trading Engine (main_realtime.py)...
start "Engine" cmd /c "%PYTHON_EXE% -m src.engine.main_realtime"

echo.
echo ---> Starting FastAPI API Server (server.py)...
start "API_Server" cmd /c "%PYTHON_EXE% -m uvicorn src.dashboard.api.server:app --host 0.0.0.0 --port 8000"

echo.
echo ---> Starting Telegram Bot Listener (bot_listener.py)...
start "Bot_Listener" cmd /c "%PYTHON_EXE% -m src.notifier.bot_listener"

echo.
echo Waiting 10 seconds for all services to initialize...
timeout /t 10 /nobreak

echo.
echo ---> Starting Streamlit Dashboard...
%PYTHON_EXE% -m streamlit run src/dashboard/streamlit/app.py

echo.
echo ==================================================
echo  All services are running.
echo ==================================================
pause
