# -*- coding: utf-8 -*-
"""트레이딩 엔진의 런타임 상태와 로직을 관리합니다."""
from __future__ import annotations
import asyncio
import datetime as dt
from typing import Optional, List, Dict, Any, Tuple
from collections import deque
import ccxt.async_support as ccxt  # 비동기 지원 ccxt 임포트
import pandas as pd
import logging

from .config_loader import load_all_configs, LoadedConfig
from .utils import get_api_keys

# --- 모듈 임포트 (오류 처리 포함) ---
try:
    from ..core.strategy_signals import get_strategy_signals
except ImportError:
    get_strategy_signals = None
    logging.error("전략 신호 생성 함수(get_strategy_signals)를 찾을 수 없습니다.")

class RuntimeManager:
    """엔진의 생명주기, 데이터, 상태, 거래 실행을 총괄하는 클래스."""
    def __init__(self):
        self._engine_task: Optional[asyncio.Task] = None
        self.strategy: Optional[str] = None
        self.symbol: Optional[str] = None
        self.is_running_flag = False
        
        # --- 상태 저장소 ---
        self._logs: deque[str] = deque(maxlen=5000)
        self._errors: deque[str] = deque(maxlen=2000)
        self._orders: deque[Dict[str, Any]] = deque(maxlen=1000)
        self._equity_curve: List[Dict[str, Any]] = []
        self._current_position: Dict[str, Any] = {}

        self._lock = asyncio.Lock()
        self._ccxt_client: Optional[ccxt.Exchange] = None
        
        # --- 설정 로드 ---
        self.config: LoadedConfig = load_all_configs()
        self._log("[설정] 설정 로드 완료.")

    # --- CCXT 클라이언트 관리 ---
    def get_client(self) -> ccxt.Exchange:
        """CCXT 거래소 클라이언트를 반환하며, 필요한 경우 초기화합니다."""
        if self._ccxt_client is None:
            api_key, api_secret = get_api_keys("bybit") # 중앙화된 함수 사용
            if not api_key or not api_secret:
                msg = "Bybit API 키가 설정되지 않았습니다. 봇을 시작할 수 없습니다."
                self._error(msg)
                raise ValueError(msg)

            is_testnet = self.config.settings.get("is_testnet", False)
            self._ccxt_client = ccxt.bybit({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                    'testnet': is_testnet,
                },
            })
            self._log(f"[CCXT] Bybit 클라이언트 초기화 완료. 테스트넷: {is_testnet}")
        return self._ccxt_client

    # --- 엔진 제어 ---
    async def start(self, strategy: str, symbol: str):
        """엔진을 시작합니다."""
        async with self._lock:
            if self.is_running_flag:
                self._log("[엔진] 이미 실행 중입니다.")
                return
            self.strategy = strategy
            self.symbol = symbol
            self.is_running_flag = True
            self._engine_task = asyncio.create_task(self._engine_loop())
            self._log(f"[엔진] 시작됨. 전략: {strategy}, 심볼: {symbol}")

    async def stop(self):
        """엔진을 중지합니다."""
        async with self._lock:
            if not self.is_running_flag or not self._engine_task:
                self._log("[엔진] 이미 중지되었습니다.")
                return
            self._engine_task.cancel()
            try:
                await self._engine_task
            except asyncio.CancelledError:
                pass # 취소는 정상 동작
            self.is_running_flag = False
            self._engine_task = None
            self._log("[엔진] 중지됨.")

    async def switch_strategy(self, strategy: str):
        """실행 중인 전략을 변경합니다."""
        async with self._lock:
            if not self.is_running_flag:
                self._error("[전략] 엔진이 실행 중이 아닐 때는 전략을 변경할 수 없습니다.")
                return
            self.strategy = strategy
            self._log(f"[전략] 전략 변경됨 → {strategy}")

    def is_running(self) -> bool:
        """엔진이 현재 실행 중인지 여부를 반환합니다."""
        return self.is_running_flag

    # --- 메인 엔진 루프 ---
    async def _engine_loop(self):
        """전략에 따라 거래를 실행하는 메인 루프."""
        if get_strategy_signals is None:
            self._error("전략 신호 생성 함수를 사용할 수 없어 엔진 루프를 시작할 수 없습니다.")
            self.is_running_flag = False
            return

        client = self.get_client()
        while self.is_running_flag:
            try:
                # 1. 데이터 가져오기 (예: 1분봉)
                ohlcv = await client.fetch_ohlcv(self.symbol, '1m', limit=100)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)

                # 2. 신호 생성
                get_strategy_signals(self.strategy, df)

                # 3. TODO: 신호에 따른 주문 실행 로직 구현
                # 예: if signals.iloc[-1]['signal'] == 1: # 매수 신호
                #         # 포지션 진입 로직
                #     elif signals.iloc[-1]['signal'] == -1: # 매도 신호
                #         # 포지션 청산 로직

                # 4. TODO: 자산 및 포지션 업데이트 로직 구현

                await asyncio.sleep(60)  # 1분 대기
            except asyncio.CancelledError:
                self._log("[엔진] 루프가 정상적으로 취소되었습니다.")
                break
            except Exception as e:
                self._error(f"[엔진 루프 오류] {e}", exc_info=True)
                await asyncio.sleep(60) # 오류 발생 시 잠시 대기 후 재시도

    # --- 상태/리포트/로그 ---
    def get_status_dict(self) -> Dict[str, Any]:
        """현재 엔진 상태를 딕셔너리로 반환합니다."""
        return {
            "running": self.is_running(),
            "strategy": self.strategy,
            "symbol": self.symbol,
            "equity": self._equity_curve[-1]['value'] if self._equity_curve else 0,
            "orders": len(self._orders),
            "errors": len(self._errors),
            "position": self._current_position
        }

    def get_logs(self, n: int) -> List[str]:
        """최근 로그 n개를 리스트로 반환합니다."""
        return list(self._logs)[-n:]

    def get_recent_orders(self, n: int) -> List[Dict[str, Any]]:
        """최근 주문 n개를 리스트로 반환합니다."""
        return list(self._orders)[-n:]

    def get_equity_series(self) -> Tuple[List, List]:
        """자산 곡선 데이터를 타임스탬프와 값의 튜플로 반환합니다."""
        if not self._equity_curve:
            return [], []
        timestamps = [item['timestamp'] for item in self._equity_curve]
        values = [item['value'] for item in self._equity_curve]
        return timestamps, values

    # --- 내부 유틸리티 ---
    def _log(self, message: str):
        """내부 로그를 기록합니다."""
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._logs.append(f"{timestamp} | {message}")

    def _error(self, message: str, exc_info: bool = False):
        """내부 오류 로그를 기록합니다."""
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._errors.append(f"{timestamp} | {message}")
        if exc_info:
            logging.error(message, exc_info=True)

    def _on_order_event(self, side: str, symbol: str, qty: float, result: Dict[str, Any]):
        """주문 발생 시 호출되는 이벤트 핸들러."""
        ret_code = result.get('retCode')
        ret_msg = result.get('retMsg')
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%m/%d %H:%M:%S")
        self._orders.append({
            "ts": timestamp, 
            "side": side, 
            "symbol": symbol, 
            "qty": qty, 
            "ret": f"{ret_code}|{ret_msg}"
        })