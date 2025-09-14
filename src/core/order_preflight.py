# -*- coding: utf-8 -*-
"""
core/order_preflight.py (v1.4 - Final Syntax Fix)
------------------------------------
📌 목적: Bybit v5 주문 전 안정성 검사 및 수량 자동 조정
- 버그 수정: try...except 블록 내 return 문의 누락된 괄호를 추가하여 구문 오류를 최종 해결합니다.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_DOWN
from typing import Union, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

Numeric = Union[Decimal, str, int, float]

def _to_decimal(value: Numeric) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")

def snap_qty(
    quantity: Numeric, step_size: Numeric,
    min_quantity: Optional[Numeric] = None, max_quantity: Optional[Numeric] = None
) -> Decimal:
    qty_decimal = _to_decimal(quantity)
    step_decimal = _to_decimal(step_size)
    if step_decimal > 0:
        qty_decimal = (qty_decimal / step_decimal).to_integral_exact(rounding=ROUND_DOWN) * step_decimal
    if min_quantity is not None and qty_decimal < _to_decimal(min_quantity):
        return Decimal("0")
    if max_quantity is not None and qty_decimal > _to_decimal(max_quantity):
        qty_decimal = _to_decimal(max_quantity)
    return qty_decimal.normalize()

def estimate_required_margin(
    price: Numeric, quantity: Numeric, leverage: Numeric = 10, 
    taker_fee: Numeric = Decimal("0.0006"), buffer: Numeric = Decimal("0.001")
) -> Tuple[Decimal, Decimal]:
    price_d, qty_d, leverage_d = _to_decimal(price), _to_decimal(quantity), _to_decimal(leverage)
    if leverage_d <= 0:
        raise ValueError("Leverage must be > 0")
    notional = price_d * qty_d
    required_margin = (notional / leverage_d) + (notional * (_to_decimal(taker_fee) + _to_decimal(buffer)))
    return required_margin, notional

def get_max_affordable_qty(
    available_balance: Numeric, price: Numeric, leverage: Numeric = 10, 
    taker_fee: Numeric = Decimal("0.0006"), buffer: Numeric = Decimal("0.001")
) -> Decimal:
    balance_d, price_d, leverage_d = _to_decimal(available_balance), _to_decimal(price), _to_decimal(leverage)
    if price_d <= 0:
        return Decimal("0")
    if leverage_d <= 0:
        raise ValueError("Leverage must be > 0")
    denominator = price_d * ((Decimal("1") / leverage_d) + _to_decimal(taker_fee) + _to_decimal(buffer))
    if denominator <= 0:
        return Decimal("0")
    max_qty = balance_d / denominator
    return max_qty if max_qty > 0 else Decimal("0")

def _get_zero_qty_reason(
    requested_qty: Numeric, max_affordable_qty: Decimal, min_qty: Numeric, available_balance: Numeric
) -> str:
    requested_d, min_qty_d = _to_decimal(requested_qty), _to_decimal(min_qty)
    if requested_d > 0 and requested_d < min_qty_d:
        return f"요청 수량({requested_d})이 최소 주문 수량({min_qty_d})보다 작습니다."
    if max_affordable_qty < min_qty_d:
        return f"가용 잔고 부족. 최대 가능 수량({max_affordable_qty:.8f})이 최소 주문 수량({min_qty_d})보다 적습니다. (가용잔고: {available_balance})"
    return f"알 수 없는 이유로 최종 수량이 0이 되었습니다. (요청: {requested_d}, 최대가능: {max_affordable_qty})"

def preflight_and_resize_qty(
    requested_qty: Numeric, price: Numeric, available_balance: Numeric,
    leverage: Numeric = 10, taker_fee: Numeric = Decimal("0.0006"),
    buffer: Numeric = Decimal("0.0015"), step_size: Numeric = Decimal("0.001"),
    min_qty: Numeric = Decimal("0.001"), max_qty: Optional[Numeric] = None,
) -> Tuple[Decimal, Dict[str, Any]]:
    try:
        max_qty_by_balance = get_max_affordable_qty(available_balance, price, leverage, taker_fee, buffer)
        target_qty = min(_to_decimal(requested_qty), max_qty_by_balance)
        final_qty = snap_qty(target_qty, step_size, min_qty, max_qty)
        required_margin, notional = estimate_required_margin(price, final_qty, leverage, taker_fee, buffer)
        
        reason = "OK"
        if final_qty == 0:
            reason = _get_zero_qty_reason(requested_qty, max_qty_by_balance, min_qty, available_balance)

        diagnosis = {
            "requested_qty": str(requested_qty), "snapped_final_qty": str(final_qty),
            "max_affordable_qty": f"{max_qty_by_balance:.8f}", "price": str(price),
            "leverage": str(leverage), "available_balance": str(available_balance),
            "notional": str(notional), "estimated_required_margin": str(required_margin),
            "reason": reason,
        }
        return final_qty, diagnosis
    except Exception as e:
        logger.error(f"주문 사전 검사 중 심각한 오류 발생: {e}", exc_info=True)
        # 누락되었던 닫는 괄호 ')'를 추가하여 구문 오류 수정
        return Decimal("0"), {"reason": f"Exception: {e}"}

# === 사용 예시 (v1.3) ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    scenarios = {
        "SCENARIO 1: NORMAL ORDER": {
            "requested_qty": Decimal("0.01"), "price": Decimal("60000"), "available_balance": Decimal("100"),
        },
        "SCENARIO 2: REQUESTED QTY < MIN QTY": {
            "requested_qty": Decimal("0.0001"), "price": Decimal("60000"), "available_balance": Decimal("100"),
            "min_qty": Decimal("0.001"),
        },
        "SCENARIO 3: INSUFFICIENT BALANCE": {
            "requested_qty": Decimal("0.1"), "price": Decimal("60000"), "available_balance": Decimal("50"),
            "min_qty": Decimal("0.001"),
        },
    }
    for name, params in scenarios.items():
        print(f"--- {name} ---")
        try:
            qty, info = preflight_and_resize_qty(**params)
            print(f"  최종 수량: {qty}")
            print(f"  정보: {info.get('reason', 'N/A')}")
        except Exception as e:
            print(f"  테스트 실행 중 오류 발생: {e}")
        print("-" * (len(name) + 4))