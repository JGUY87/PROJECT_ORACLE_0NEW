# -*- coding: utf-8 -*-
"""
FastAPI 웹 애플리케이션의 메인 파일
"""
import logging
from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..engine.manager import TradingEngine
from ..core.database import get_db
from ..core.models import SignalLog

# FastAPI 앱 인스턴스 생성
app = FastAPI(title="Crypto Trading Bot Dashboard")

# Jinja2 템플릿 설정
# 이 경로가 프로젝트 루트에서 실행되는 것을 기준으로 합니다.
templates = Jinja2Templates(directory="src/web/templates")

# TradingEngine 싱글턴 인스턴스 가져오기
engine = TradingEngine()

@app.get("/")
async def get_dashboard(request: Request, db: Session = Depends(get_db)):
    """
    메인 대시보드 페이지를 렌더링합니다.
    """
    status = engine.get_status()
    try:
        recent_signals = db.query(SignalLog).order_by(SignalLog.timestamp.desc()).limit(10).all()
    except Exception as e:
        logging.error(f"Failed to fetch signals for dashboard: {e}")
        recent_signals = []
        
    return templates.TemplateResponse(
        "index.html", 
        {
            "request": request, 
            "status": status,
            "signals": recent_signals
        }
    )

@app.get("/api/status")
async def api_get_status():
    """
    현재 엔진 상태를 JSON으로 반환하는 API 엔드포인트
    """
    return engine.get_status()

@app.get("/api/signals")
async def api_get_signals(db: Session = Depends(get_db)):
    """
    최근 신호 로그 20개를 JSON으로 반환하는 API 엔드포인트
    """
    try:
        signals = db.query(SignalLog).order_by(SignalLog.timestamp.desc()).limit(20).all()
        return signals
    except Exception as e:
        logging.error(f"Failed to fetch API signals: {e}")
        return {"error": "Could not fetch signals"}
