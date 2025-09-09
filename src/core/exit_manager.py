# -*- coding: utf-8 -*-
"""
🛡️ exit_manager.py — 포지션 청산 및 트레일링 스톱 관리 모듈

- TP1/TP2/트레일링/손절 로직을 중앙에서 관리합니다.
- 비동기 `ccxt` 클라이언트를 사용하여 거래소와 상호작용합니다.
- `pandas-ta`를 사용하여 기술적 지표를 계산합니다.
"""
from __future__ import annotations
import logging
import math
from dataclasses import dataclass
from typing import Optional, Dict, Any

import ccxt.async_support as ccxt
import pandas as pd
import pandas_ta as ta

# --- 프로젝트 내 모듈 임포트 ---
# 중앙화된 ExitProfile 정의를 가져옵니다.
from .trader_exit_profiles import ExitProfile, PROFILES

# ============================================================
# 상태 모델
# ============================================================
@dataclass
class PositionState:
    """📊 포지션의 현재 상태를 저장하는 데이터 클래스."""
    symbol: str
    side: str  # "long" 또는 "short"
    entry_price: float
    qty: float
    strategy: str
    realized_tp1: bool = False   # ✅ TP1 달성 여부
    realized_tp2: bool = False   # ✅ TP2 달성 여부
    runner_qty: float = 0.0      # 🏃 러너 포지션 수량
    tp1_price: Optional[float] = None  # 🎯 TP1 가격
    tp2_price: Optional[float] = None  # 🎯 TP2 가격
    sl_price: Optional[float] = None   # ❌ 손절 가격
    trail_price: Optional[float] = None  # 📉 트레일링 스톱 가격

# ============================================================
# 컨트롤러
# ============================================================
class ExitController:
    """
    🎛️ 전략별 청산 로직을 관리하는 비동기 컨트롤러.
    """
    def __init__(self, client: ccxt.Exchange, strategy: str):
        self.client = client  # 비동기 ccxt 클라이언트
        if strategy not in PROFILES:
            logging.warning(f"'{strategy}' 프로필을 찾을 수 없어 기본 'snake_ma' 프로필을 사용합니다.")
            self.profile: ExitProfile = PROFILES["snake_ma"]
        else:
            self.profile: ExitProfile = PROFILES[strategy]

    # -------------------------- 내부 유틸리티 --------------------------
    @staticmethod
    def _last(series: pd.Series) -> float:
        """시리즈의 마지막 값을 안전하게 float로 반환합니다."""
        if series.empty:
            return 0.0
        return float(series.iloc[-1])

    # -------------------------- 등록 및 계산 --------------------------
    async def register_position(self, ps: PositionState, df: pd.DataFrame) -> PositionState:
        """
        📝 새로운 포지션을 등록하고 TP/SL 가격을 계산합니다.
        초기 손절 주문을 거래소에 전송합니다.
        
        Args:
            ps (PositionState): 현재 포지션 상태.
            df (pd.DataFrame): OHLCV 데이터프레임.

        Returns:
            PositionState: TP/SL 가격이 계산된 포지션 상태.
        """
        # 📊 ATR/EMA 지표 계산
        atr_val = self._last(ta.atr(df["high"], df["low"], df["close"], length=14))
        ema_base = self._last(ta.ema(df["close"], length=self.profile.trail_ema_span))

        # ❌ 손절 가격 계산
        risk_per_unit = self.profile.sl_atr_mult * atr_val
        if ps.side == "long":
            ps.sl_price = ps.entry_price - risk_per_unit
        else:
            ps.sl_price = ps.entry_price + risk_per_unit

        # 🎯 TP1/TP2 가격 계산
        sign = 1 if ps.side == "long" else -1
        ps.tp1_price = ps.entry_price + (self.profile.tp1_r * risk_per_unit) * sign
        ps.tp2_price = ps.entry_price + (self.profile.tp2_r * risk_per_unit) * sign

        # 📉 트레일링 시작 가격 초기화
        ps.trail_price = min(ema_base, ps.entry_price) if ps.side == "long" else max(ema_base, ps.entry_price)

        # 🛡️ 초기 손절 주문 전송 (거래소 API 사용)
        try:
            await self.client.create_order(
                symbol=ps.symbol,
                type="stop_market", # Bybit v5는 stop_market을 사용
                side="sell" if ps.side == "long" else "buy",
                amount=ps.qty,
                params={"triggerPrice": ps.sl_price, "reduceOnly": True},
            )
            logging.info(f"[{ps.symbol}] 손절 주문 설정 완료: {ps.sl_price:.4f}")
        except Exception as e:
            logging.error(f"[{ps.symbol}] 손절 주문 설정 실패: {e}", exc_info=True)
            # 손절 주문 실패는 심각한 문제일 수 있으므로, 상위 로직에서 처리 필요

        return ps

    # -------------------------- 평가 및 실행 --------------------------
    async def evaluate_and_act(self, ps: PositionState, df: pd.DataFrame) -> Dict[str, Any]:
        """
        🔎 포지션 상태를 평가하고, 필요한 경우 청산/부분 익절 주문을 실행합니다.
        """
        current_price = self._last(df["close"])
        atr_val = self._last(ta.atr(df["high"], df["low"], df["close"], length=14))
        ema_val = self._last(ta.ema(df["close"], length=self.profile.trail_ema_span))

        # 🎯 TP1 / TP2 익절 확인
        if not ps.realized_tp1 and ((ps.side == "long" and current_price >= ps.tp1_price) or (ps.side == "short" and current_price <= ps.tp1_price)):
            return await self._execute_tp(ps, "tp1", current_price)

        if ps.realized_tp1 and not ps.realized_tp2 and ((ps.side == "long" and current_price >= ps.tp2_price) or (ps.side == "short" and current_price <= ps.tp2_price)):
            return await self._execute_tp(ps, "tp2", current_price)

        # 📉 트레일링 스톱 확인
        trail_buffer = self.profile.trail_atr_mult * atr_val
        if ps.side == "long":
            new_trail_price = max(ps.trail_price or -math.inf, ema_val - trail_buffer)
            if current_price <= new_trail_price:
                return await self._close_all(ps, current_price, "trail_stop_long")
            ps.trail_price = new_trail_price
        else: # short
            new_trail_price = min(ps.trail_price or math.inf, ema_val + trail_buffer)
            if current_price >= new_trail_price:
                return await self._close_all(ps, current_price, "trail_stop_short")
            ps.trail_price = new_trail_price

        # ❌ 손절 확인 (백업용, 주로 거래소의 stop_market 주문에 의존)
        if (ps.side == "long" and current_price <= ps.sl_price) or (ps.side == "short" and current_price >= ps.sl_price):
            return await self._close_all(ps, current_price, "stop_loss_manual")

        return {"action": "hold", "reason": "no_condition_met"}

    # -------------------------- 내부 실행 함수 --------------------------
    async def _execute_tp(self, ps: PositionState, portion: str, price: float) -> Dict[str, Any]:
        """💰 부분 익절 주문을 실행합니다."""
        qty_to_close = 0.0
        if portion == "tp1":
            qty_to_close = ps.qty * self.profile.tp1_pct
            ps.realized_tp1 = True
        elif portion == "tp2":
            qty_to_close = ps.qty * self.profile.tp2_pct
            ps.realized_tp2 = True

        if qty_to_close <= 0:
            return {"action": "noop", "reason": "zero_qty"}

        logging.info(f"[{ps.symbol}] {portion.upper()} 익절 실행 (수량: {qty_to_close:.4f}) @ {price:.4f}")
        return await self._place_reduce_order(ps, qty_to_close, f"take_profit_{portion}")

    async def _close_all(self, ps: PositionState, price: float, reason: str) -> Dict[str, Any]:
        """🛑 남은 포지션 전체를 청산합니다."""
        remaining_qty = ps.qty * (1 - (self.profile.tp1_pct if ps.realized_tp1 else 0) - (self.profile.tp2_pct if ps.realized_tp2 else 0))
        logging.info(f"[{ps.symbol}] 전체 청산 실행 (수량: {remaining_qty:.4f}) @ {price:.4f}, 사유: {reason}")
        return await self._place_reduce_order(ps, remaining_qty, reason)

    async def _place_reduce_order(self, ps: PositionState, qty: float, reason: str) -> Dict[str, Any]:
        """실제 청산 주문을 전송하는 내부 함수."""
        side = "sell" if ps.side == "long" else "buy"
        try:
            response = await self.client.create_order(
                symbol=ps.symbol,
                type="market",
                side=side,
                amount=qty,
                params={"reduceOnly": True},
            )
            logging.info(f"[{ps.symbol}] 청산 주문 성공. 응답: {response}")
            return {"action": "order_sent", "reason": reason, "qty": qty, "response": response}
        except ccxt.NetworkError as e:
            logging.error(f"[{ps.symbol}] 청산 주문 네트워크 오류: {e}")
        except ccxt.ExchangeError as e:
            logging.error(f"[{ps.symbol}] 청산 주문 거래소 오류: {e}")
        except Exception as e:
            logging.error(f"[{ps.symbol}] 청산 주문 중 알 수 없는 오류: {e}", exc_info=True)
        
        return {"action": "order_failed", "reason": reason, "qty": qty}