# -*- coding: utf-8 -*-
"""
dashboard/api/server.py

Communicates with the running main_realtime.py engine via command_manager (file IPC).
"""
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import pandas as pd
from pathlib import Path
import sys

# --- Path Setup ---
project_root = Path(__file__).resolve().parents[3]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# --- Module Imports ---
from src import command_manager as cm
from src.core.balance_utils import get_usdt_balance_and_krw

# --- File Paths ---
STATUS_FILE = project_root / "outputs/engine_status.json"
TRADE_LOG_FILE = project_root / "outputs/live_logs/trade_log.csv"

# --- FastAPI App Initialization ---
app = FastAPI(title="PROJECT_ORACLE_0 Dashboard API", version="3.1.0-ipc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helper to send command and await result ---
async def send_and_await(command: str, params: dict = None, timeout: int = 15):
    try:
        result = await cm.send_command(command, params or {}, timeout)
        if not result:
            raise HTTPException(status_code=408, detail="Engine did not respond in time.")
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message", "Engine returned an error."))
        return result
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to communicate with engine: {str(e)}")

# --- API Routes ---

@app.get("/")
async def root():
    return {"message": "Dashboard API (IPC mode) is running."}

@app.get("/api/status")
async def api_status():
    if not STATUS_FILE.exists():
        raise HTTPException(status_code=404, detail="Status file not found.")
    with open(STATUS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

@app.get("/api/equity_chart.png")
async def api_equity_chart():
    # This feature is not supported by the main_realtime.py engine.
    return Response(content=b"", media_type="image/png")

@app.get("/api/trades")
async def api_trades(limit: int = 50):
    if not TRADE_LOG_FILE.exists():
        return {"rows": []}
    try:
        df = pd.read_csv(TRADE_LOG_FILE)
        return {"rows": df.tail(limit).to_dict('records')}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read trade log: {e}")

@app.get("/api/logs")
async def api_logs(limit: int = 100):
    return {"lines": ["Log viewing via API is not supported in this mode.", "Check the console output of the main engine."]}

@app.get("/api/balance")
async def api_balance():
    try:
        return await get_usdt_balance_and_krw()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get balance: {str(e)}")

# --- Engine Control Routes ---

@app.post("/api/run")
async def api_run():
    return await send_and_await("engine_resume")

@app.post("/api/stop")
async def api_stop():
    return await send_and_await("stop_engine")
