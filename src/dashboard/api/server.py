# -*- coding: utf-8 -*-
"""
dashboard/api/server.py — FastAPI 대시보드 서버 (최적화 버전)

사용법:
uvicorn src.dashboard.api.server:app --port 8000 --reload

기능:
- API 엔드포인트: /api/status, /api/equity, /api/trades, /api/logs
- /api/balance: USDT 잔고 및 원화 환산 가치 조회
- /api/run|stop|restart|switch_strategy: 실시간 트레이딩 엔진 제어
- /api/equity_chart.png: 누적 수익률 차트 이미지
- 정적 페이지: / 또는 /web/ (src/dashboard/web/index.html 제공)

주의:
* 이 서버에서 엔진을 실행하면 텔레그램 봇과 충돌이 발생할 수 있습니다.
  텔레그램 봇이 이미 엔진을 실행 중인 경우, 이 대시보드는 조회 전용으로 사용하세요.
"""
from __future__ import annotations
import os
import io
import asyncio
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Body, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, Response, JSONResponse
import matplotlib.pyplot as plt
import pandas as pd

# --- 모듈 임포트 ---
try:
    from src.engine.runtime_manager import RuntimeManager
except ImportError:
    RuntimeManager = None

try:
    from src.notifier.telegram_bot.balance import get_usdt_balance_and_krw
except ImportError:
    get_usdt_balance_and_krw = None

# --- FastAPI 앱 초기화 ---
app = FastAPI(title="PROJECT_ORACLE_0 대시보드 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 정적 파일 설정 ---
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web"))
if os.path.isdir(static_dir):
    app.mount("/web", StaticFiles(directory=static_dir, html=True), name="web")

# --- 런타임 브리지 (싱글턴) ---
class RuntimeBridge:
    def __init__(self):
        self.rt: Optional[RuntimeManager] = None
        self.lock = asyncio.Lock()

    def get_runtime(self) -> Optional[RuntimeManager]:
        return self.rt

    async def start(self, strategy: str, symbol: str):
        if RuntimeManager is None:
            raise HTTPException(status_code=501, detail="트레이딩 엔진 모듈(RuntimeManager)을 사용할 수 없습니다.")
        async with self.lock:
            if self.rt and self.rt.is_running():
                raise HTTPException(status_code=409, detail="엔진이 이미 실행 중입니다.")
            self.rt = RuntimeManager()
            await self.rt.start(strategy=strategy, symbol=symbol)

    async def stop(self):
        async with self.lock:
            if self.rt and self.rt.is_running():
                await self.rt.stop()
                self.rt = None # 인스턴스 정리

    async def restart(self, strategy: Optional[str] = None, symbol: Optional[str] = None):
        async with self.lock:
            if self.rt and self.rt.is_running():
                await self.rt.stop()
            
            if RuntimeManager is None:
                raise HTTPException(status_code=501, detail="트레이딩 엔진 모듈(RuntimeManager)을 사용할 수 없습니다.")

            self.rt = RuntimeManager()
            await self.rt.start(
                strategy=strategy or "snake_ma",
                symbol=symbol or "BTCUSDT"
            )

    async def switch_strategy(self, strategy: str):
        if not self.rt or not self.rt.is_running():
            raise HTTPException(status_code=409, detail="엔진이 실행되고 있지 않습니다.")
        await self.rt.switch_strategy(strategy)

# --- 의존성 주입을 위한 브리지 인스턴스 --- 
bridge = RuntimeBridge()

def get_bridge() -> RuntimeBridge:
    return bridge

# --- API 라우트 ---

@app.get("/")
async def root():
    """웹 인터페이스가 있는 경우 리디렉션합니다."""
    if os.path.isdir(static_dir):
        return RedirectResponse(url="/web/")
    return {"message": "대시보드 API가 실행 중입니다. 웹 UI를 찾을 수 없습니다."}

@app.get("/api/status")
async def api_status(bridge: RuntimeBridge = Depends(get_bridge)) -> Dict[str, Any]:
    """트레이딩 엔진의 현재 상태를 가져옵니다."""
    rt = bridge.get_runtime()
    if not rt or not rt.is_running():
        return {"running": False, "strategy": None, "symbol": None, "equity": 0, "orders": 0, "errors": 0}
    return rt.status_dict()

@app.get("/api/equity")
async def api_equity(bridge: RuntimeBridge = Depends(get_bridge)) -> Dict[str, List]:
    """자산 곡선 데이터를 가져옵니다."""
    rt = bridge.get_runtime()
    if not rt:
        return {"timestamps": [], "equity": []}
    ts, eq = rt.equity_series()
    return {"timestamps": ts, "equity": eq}

@app.get("/api/equity_chart.png")
async def api_equity_chart(bridge: RuntimeBridge = Depends(get_bridge)):
    """자산 차트의 PNG 이미지를 반환합니다."""
    rt = bridge.get_runtime()
    if not rt:
        raise HTTPException(status_code=404, detail="사용 가능한 자산 데이터가 없습니다.")

    timestamps, equity = rt.equity_series()
    if not timestamps or not equity:
        raise HTTPException(status_code=404, detail="사용 가능한 자산 데이터가 없습니다.")

    df = pd.DataFrame(data={'equity': equity}, index=pd.to_datetime(timestamps, unit='s'))
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6))
    df['equity'].plot(ax=ax, color='#00ff00')
    
    ax.set_title('자산 곡선', color='white')
    ax.set_xlabel('시간', color='white')
    ax.set_ylabel('자산 (USDT)', color='white')
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, color='#555555')
    plt.xticks(rotation=45)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    
    return Response(content=buf.getvalue(), media_type="image/png")

@app.get("/api/trades")
async def api_trades(limit: int = 100, bridge: RuntimeBridge = Depends(get_bridge)) -> Dict[str, List[Dict[str, Any]]]:
    """최근 거래 목록을 가져옵니다."""
    rt = bridge.get_runtime()
    if not rt:
        return {"rows": []}
    return {"rows": rt.get_recent_orders(limit)}

@app.get("/api/logs")
async def api_logs(limit: int = 200, bridge: RuntimeBridge = Depends(get_bridge)) -> Dict[str, List[str]]:
    """최근 로그 항목을 가져옵니다."""
    rt = bridge.get_runtime()
    if not rt:
        return {"lines": []}
    return {"lines": rt.tail_logs(limit)}

@app.get("/api/balance")
async def api_balance() -> Dict[str, Any]:
    """현재 USDT 및 예상 원화 잔고를 가져옵니다."""
    if get_usdt_balance_and_krw is None:
        raise HTTPException(status_code=501, detail="잔고 모듈을 사용할 수 없습니다.")
    try:
        return get_usdt_balance_and_krw()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 엔진 제어 라우트 ---

@app.post("/api/run")
async def api_run(payload: Dict[str, Any] = Body(...), bridge: RuntimeBridge = Depends(get_bridge)):
    """주어진 전략과 심볼로 트레이딩 엔진을 시작합니다."""
    strategy = payload.get("strategy", "snake_ma")
    symbol = payload.get("symbol", "BTCUSDT")
    await bridge.start(strategy=strategy, symbol=symbol)
    return {"ok": True, "message": f"'{strategy}' 전략으로 '{symbol}' 심볼에 대한 엔진을 시작했습니다."}

@app.post("/api/stop")
async def api_stop(bridge: RuntimeBridge = Depends(get_bridge)):
    """트레이딩 엔진을 중지합니다."""
    await bridge.stop()
    return {"ok": True, "message": "엔진을 중지했습니다."}

@app.post("/api/restart")
async def api_restart(payload: Dict[str, Any] = Body(None), bridge: RuntimeBridge = Depends(get_bridge)):
    """트레이딩 엔진을 재시작합니다."""
    strategy = payload.get("strategy") if payload else None
    symbol = payload.get("symbol") if payload else None
    await bridge.restart(strategy=strategy, symbol=symbol)
    return {"ok": True, "message": "엔진을 재시작했습니다."}

@app.post("/api/switch_strategy")
async def api_switch_strategy(payload: Dict[str, Any] = Body(...), bridge: RuntimeBridge = Depends(get_bridge)):
    """실행 중인 엔진의 전략을 전환합니다."""
    strategy = payload.get("strategy")
    if not strategy:
        raise HTTPException(status_code=400, detail="'strategy' 필드는 필수입니다.")
    await bridge.switch_strategy(strategy)
    return {"ok": True, "message": f"전략을 '{strategy}'(으)로 전환했습니다."}