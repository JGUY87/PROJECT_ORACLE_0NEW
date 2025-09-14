# src/core/rl/action_schemes.py
# -*- coding: utf-8 -*-
"""
액션 스킴 & 포지션 시뮬레이터
- discrete 9-action 스킴(기본)을 실제 거래 행위로 변환하고 비용을 계산합니다.
- 버그 수정: 매수/매도 방향에 따른 슬리피지 계산을 정확하게 수정했습니다.
- 구조 개선: Enum과 헬퍼 함수를 도입하여 가독성과 유지보수성을 높였습니다.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
from enum import IntEnum

class TradeAction(IntEnum):
    """거래 액션을 정의하는 열거형"""
    HOLD = 0
    OPEN_LONG_WEAK = 1
    OPEN_LONG_STRONG = 2
    OPEN_SHORT_WEAK = 3
    OPEN_SHORT_STRONG = 4
    CLOSE = 5
    ADD_POSITION = 6
    REDUCE_POSITION = 7
    REVERSE_POSITION = 8

@dataclass
class TradeConfig:
    """거래 비용 및 정책 설정을 위한 데이터 클래스"""
    taker_fee: float = 0.00055
    slippage_bps: float = 2.0
    max_leverage: float = 10.0

def _get_execution_price(price: float, bps: float, trade_side: int) -> float:
    """
    거래 방향(매수/매도)을 고려하여 슬리피지가 적용된 체결 가격을 계산합니다.
    - trade_side: 1 for buy, -1 for sell
    """
    slippage_multiplier = 1 + (trade_side * bps / 10000.0)
    return price * slippage_multiplier

def _calculate_costs(quantity: float, exec_price: float, fee_rate: float) -> float:
    """거래 비용을 계산합니다."""
    return quantity * exec_price * fee_rate

def apply_action(
    action: int,
    price: float,
    side: int,
    size: float,
    equity: float,
    leverage: float,
    cfg: TradeConfig,
    target_notional_frac: float = 0.1
) -> Tuple[int, float, float, float]:
    """
    주어진 액션을 바탕으로 새로운 포지션 상태와 거래 비용을 계산하여 반환합니다.
    Returns: (new_side, new_size, trade_costs, exec_price)
    """
    try:
        trade_action = TradeAction(action)
    except ValueError:
        # 유효하지 않은 액션이면 HOLD 처리
        return side, size, 0.0, price

    target_notional = equity * target_notional_frac * max(1.0, leverage)
    
    # 액션에 따라 핸들러 호출
    handler_map = {
        TradeAction.HOLD: _handle_hold,
        TradeAction.OPEN_LONG_WEAK: _handle_open,
        TradeAction.OPEN_LONG_STRONG: _handle_open,
        TradeAction.OPEN_SHORT_WEAK: _handle_open,
        TradeAction.OPEN_SHORT_STRONG: _handle_open,
        TradeAction.CLOSE: _handle_close,
        TradeAction.ADD_POSITION: _handle_add,
        TradeAction.REDUCE_POSITION: _handle_reduce,
        TradeAction.REVERSE_POSITION: _handle_reverse,
    }
    
    handler = handler_map.get(trade_action, _handle_hold)
    return handler(trade_action, price, side, size, cfg, target_notional)

# --- 액션 핸들러 ---

def _handle_hold(*args) -> Tuple[int, float, float, float]:
    price, side, size, _, _ = args[1:6]
    return side, size, 0.0, price

def _handle_open(action: TradeAction, price: float, side: int, size: float, cfg: TradeConfig, target_notional: float) -> Tuple[int, float, float, float]:
    strength = 2.0 if action in [TradeAction.OPEN_LONG_STRONG, TradeAction.OPEN_SHORT_STRONG] else 1.0
    qty = (target_notional * strength) / max(price, 1e-9)
    
    new_side = 1 if action in [TradeAction.OPEN_LONG_WEAK, TradeAction.OPEN_LONG_STRONG] else -1
    
    exec_price = _get_execution_price(price, cfg.slippage_bps, trade_side=new_side)
    costs = _calculate_costs(qty, exec_price, cfg.taker_fee)
    
    return new_side, qty, costs, exec_price

def _handle_close(action: TradeAction, price: float, side: int, size: float, cfg: TradeConfig, target_notional: float) -> Tuple[int, float, float, float]:
    if size <= 0:
        return side, size, 0.0, price
        
    # 포지션 청산은 현재 포지션의 반대 방향 거래
    exec_price = _get_execution_price(price, cfg.slippage_bps, trade_side=-side)
    costs = _calculate_costs(size, exec_price, cfg.taker_fee)
    
    return 0, 0.0, costs, exec_price

def _handle_add(action: TradeAction, price: float, side: int, size: float, cfg: TradeConfig, target_notional: float) -> Tuple[int, float, float, float]:
    if side == 0:
        return side, size, 0.0, price
        
    add_qty = size * 0.5
    exec_price = _get_execution_price(price, cfg.slippage_bps, trade_side=side)
    costs = _calculate_costs(add_qty, exec_price, cfg.taker_fee)
    
    return side, size + add_qty, costs, exec_price

def _handle_reduce(action: TradeAction, price: float, side: int, size: float, cfg: TradeConfig, target_notional: float) -> Tuple[int, float, float, float]:
    if side == 0 or size <= 0:
        return side, size, 0.0, price
        
    reduce_qty = size * 0.5
    exec_price = _get_execution_price(price, cfg.slippage_bps, trade_side=-side)
    costs = _calculate_costs(reduce_qty, exec_price, cfg.taker_fee)
    
    new_size = max(0.0, size - reduce_qty)
    new_side = side if new_size > 0 else 0
    
    return new_side, new_size, costs, exec_price

def _handle_reverse(action: TradeAction, price: float, side: int, size: float, cfg: TradeConfig, target_notional: float) -> Tuple[int, float, float, float]:
    if side == 0: # 포지션 없으면 신규 롱 진입
        return _handle_open(TradeAction.OPEN_LONG_WEAK, price, side, size, cfg, target_notional)

    # 1. 기존 포지션 청산
    close_exec_price = _get_execution_price(price, cfg.slippage_bps, trade_side=-side)
    close_costs = _calculate_costs(size, close_exec_price, cfg.taker_fee)
    
    # 2. 반대 방향 신규 진입
    new_side = -side
    new_size = size # 동일 수량으로 반대 포지션 진입
    open_exec_price = _get_execution_price(price, cfg.slippage_bps, trade_side=new_side)
    open_costs = _calculate_costs(new_size, open_exec_price, cfg.taker_fee)
    
    total_costs = close_costs + open_costs
    # 체결가는 신규 포지션의 체결가로 통일
    return new_side, new_size, total_costs, open_exec_price

def unrealized_pnl(side: int, size: float, entry_price: float, price: float) -> float:
    """미실현 손익을 계산합니다."""
    if side == 0 or size <= 0 or entry_price <= 0:
        return 0.0
    
    price_diff = price - entry_price
    return price_diff * size * side