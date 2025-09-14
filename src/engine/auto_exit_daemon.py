# -*- coding: utf-8 -*-
"""
src/engine/auto_exit_daemon.py — 확장버전 v2.4 (Poetry 구성 정합 리팩토링)
- 목표: 네가 제시한 pyproject.toml( Poety, ccxt/aiohttp/loguru 등 )과 100% 정합
- 의존성: ccxt, aiohttp, loguru (python-dotenv/pybit 없어도 동작)
- 기능: TP1/TP2 분할 익절, SL, 트레일링 스톱 자동 관리(비동기)
- 운영: 병렬 처리, 지수 백오프, 상태 원자 저장(JSON), 수량/가격 정밀도 반올림
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# =========================
# 로깅 설정
# =========================
def setup_logging():
    """Loguru 로거를 설정하거나, 없을 경우 표준 로거로 대체합니다."""
    try:
        from loguru import logger
        logger.remove()
        logger.add(lambda msg: print(msg, end=""), colorize=True, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
        return logger
    except ImportError:
        import logging
        return logging.getLogger(__name__)

# =========================
# 설정 (dataclass 기반)
# =========================
@dataclass
class Config:
    """환경 변수 또는 기본값으로 설정을 관리합니다."""
    scan_sec: float = float(os.getenv("AUTOEXIT_SCAN_SEC", "2.0"))
    max_concurrency: int = int(os.getenv("AUTOEXIT_MAX_CONCURRENCY", "4"))
    err_backoff_base: float = float(os.getenv("AUTOEXIT_ERR_BACKOFF_BASE", "2.0"))
    err_backoff_max: float = float(os.getenv("AUTOEXIT_ERR_BACKOFF_MAX", "60.0"))
    
    tp_pct: float = float(os.getenv("AUTOEXIT_TP_PCT", "0.008"))
    sl_pct: float = float(os.getenv("AUTOEXIT_SL_PCT", "0.005"))
    trail_pct: float = float(os.getenv("AUTOEXIT_TRAIL_PCT", "0.006"))
    
    tp1_ratio: float = float(os.getenv("AUTOEXIT_TP1_RATIO", "0.5"))
    tp2_ratio: float = float(os.getenv("AUTOEXIT_TP2_RATIO", "0.5"))
    tp2_extra_pct: float = float(os.getenv("AUTOEXIT_TP2_EXTRA_PCT", "0.004"))
    
    symbol_allowlist: List[str] = field(default_factory=lambda: [
        s.strip() for s in os.getenv("AUTOEXIT_SYMBOLS", "").split(",") if s.strip()
    ])
    
    telegram_token: str = os.getenv("AUTOEXIT_TG_TOKEN", "")
    telegram_chat_id: str = os.getenv("AUTOEXIT_TG_CHAT_ID", "")
    
    @property
    def is_telegram_enabled(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

# --- 전역 객체 ---
config = Config()
LOG = setup_logging()
KST = timezone(timedelta(hours=9))
STATE_PATH = Path("outputs") / "auto_exit_state.json"
STATE_PATH.parent.mkdir(exist_ok=True)

# =========================
# 유틸
# =========================
def now_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _atomic_save(path: str, obj: Any):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(tmp, path)


def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _slim_state(st: Dict[str, Any], keep: List[str]) -> Dict[str, Any]:
    slim: Dict[str, Any] = {}
    for sym in keep:
        if sym in st:
            slim[sym] = st[sym]
    return slim

# ===== 포지션/티커 유틸 =====
def _pos_contracts(p: Dict[str, Any]) -> float:
    for k in ("contracts", "contractSize", "size", "amount", "positionAmt", "qty"):
        v = p.get(k)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0


def _pos_side(p: Dict[str, Any]) -> Optional[str]:
    """포지션 딕셔너리에서 'side' 정보를 추출합니다."""
    side = p.get("side")
    if isinstance(side, str):
        side = side.lower()
        if "long" in side:
            return "long"
        if "short" in side or "sell" in side:
            return "short"
    
    # 'contracts' 또는 유사한 키의 부호로 판단
    contracts = _pos_contracts(p)
    if contracts > 0:
        return "long"
    if contracts < 0:
        return "short"
        
    return None
