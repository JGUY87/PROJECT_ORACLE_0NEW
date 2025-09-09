# src/core/rl/action_schemes.py
# -*- coding: utf-8 -*-
"""
액션 스킴 & 포지션 시뮬레이터
- discrete 9-action 스킴(기본): [HOLD, OPEN_L1, OPEN_L2, OPEN_S1, OPEN_S2, CLOSE, ADD, REDUCE, REVERSE]
- 포지션/증거금/수수료/슬리피지/펀딩 계산
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple

@dataclass
class TradeConfig:
    taker_fee: float = 0.00055          # 5.5bps
    maker_fee: float = 0.0001
    slippage_bps: float = 2.0           # 2bps
    max_leverage: float = 10.0
    funding_rate_hourly: float = 0.0    # 보수적 기본 0

def _slippage(price: float, bps: float) -> float:
    return price * (1 + bps/10000.0)

def apply_action(
    action: int,
    price: float,
    side: int,                       # -1/0/1
    size: float,                     # 코인 수량
    equity: float,
    leverage: float,
    cfg: TradeConfig,
    target_notional_frac: float = 0.1
) -> Tuple[int, float, float, float]:
    """
    포지션 상태 갱신:
    - 반환: (new_side, new_size, trade_costs, exec_price)
    """
    exec_price = price
    trade_costs = 0.0
    new_side, new_size = side, size
    fee_rate = cfg.taker_fee

    if action == 0:  # HOLD
        return side, size, 0.0, price

    # 목표 명목가(에쿼티 * frac * 레버리지)
    target_notional = equity * target_notional_frac * max(1.0, leverage)

    if action in (1,2):  # OPEN LONG (약/강)
        qty = (target_notional * (1.0 if action==1 else 2.0)) / max(price, 1e-9)
        exec_price = _slippage(price, cfg.slippage_bps)
        trade_costs = qty * exec_price * fee_rate
        new_side = 1
        new_size = qty

    elif action in (3,4):  # OPEN SHORT (약/강)
        qty = (target_notional * (1.0 if action==3 else 2.0)) / max(price, 1e-9)
        exec_price = _slippage(price, cfg.slippage_bps)
        trade_costs = qty * exec_price * fee_rate
        new_side = -1
        new_size = qty

    elif action == 5:  # CLOSE
        if size > 0:
            exec_price = _slippage(price, cfg.slippage_bps)
            trade_costs = size * exec_price * fee_rate
        new_side = 0
        new_size = 0.0

    elif action == 6:  # ADD 50%
        if side != 0:
            add_qty = size * 0.5
            exec_price = _slippage(price, cfg.slippage_bps)
            trade_costs = add_qty * exec_price * fee_rate
            new_size = size + add_qty

    elif action == 7:  # REDUCE 50%
        if side != 0 and size > 0:
            red_qty = size * 0.5
            exec_price = _slippage(price, cfg.slippage_bps)
            trade_costs = red_qty * exec_price * fee_rate
            new_size = max(0.0, size - red_qty)
            if new_size == 0.0:
                new_side = 0

    elif action == 8:  # REVERSE
        # 기존 포지션 청산 + 반대 방향 진입(동일 크기)
        if size > 0:
            exec_price = _slippage(price, cfg.slippage_bps)
            trade_costs += size * exec_price * fee_rate
        new_side = -side if side != 0 else 1
        new_size = size if size > 0 else (target_notional / max(price, 1e-9))
        exec_price = _slippage(price, cfg.slippage_bps)
        trade_costs += new_size * exec_price * fee_rate

    return new_side, new_size, trade_costs, exec_price

def unrealized_pnl(side: int, size: float, entry_price: float, price: float) -> float:
    if side == 0 or size <= 0 or entry_price <= 0:
        return 0.0
    if side > 0:
        return (price - entry_price) * size
    else:
        return (entry_price - price) * size
