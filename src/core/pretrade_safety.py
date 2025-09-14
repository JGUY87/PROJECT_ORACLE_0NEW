# -*- coding: utf-8 -*-
"""
src/core/pretrade_safety.py
============================================================
📌 목적
- 주문 전 안전성 검사 및 **잔고 부족 시 자동 감량 재시도** (CCXT 기반)
- qtyStep/minOrderQty 보정과 함께 **시장가 주문 안전 래핑**
============================================================
"""
from __future__ import annotations
import math
import time
import logging
from typing import Dict, Any
import ccxt

# 로거 설정
logger = logging.getLogger(__name__)

def _reduce_qty(
    quantity: float,
    rate: float = 0.9,
    min_qty: float = 0.0,
    step: float = 0.0
) -> float:
    """
    주문 수량을 지정된 비율로 감소시키고, 최소 수량 및 스텝에 맞춰 조정합니다.

    Args:
        quantity (float): 현재 수량.
        rate (float): 감소 비율 (예: 0.9는 10% 감소).
        min_qty (float): 최소 주문 수량.
        step (float): 수량 스텝.

    Returns:
        float: 조정된 수량.
    """
    reduced_qty = max(quantity * rate, min_qty)
    if step and step > 0:
        reduced_qty = math.floor(reduced_qty / step) * step
    return max(reduced_qty, min_qty)

def safe_market_order(
    client: ccxt.Exchange, *,
    symbol: str,
    side: str,
    qty: float,
    reduce_only: bool = False,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    🛡️ 시장가 주문 안전 래퍼 (CCXT 기반)
    - InsufficientFunds 에러 발생 시 수량을 자동으로 줄여 재시도합니다.

    Args:
        client (ccxt.Exchange): CCXT 거래소 클라이언트 객체.
        symbol (str): 거래 심볼 (예: 'BTC/USDT:USDT').
        side (str): 주문 방향 ('buy' 또는 'sell').
        qty (float): 주문 수량.
        reduce_only (bool): 포지션 축소만 허용할지 여부.
        max_retries (int): 최대 재시도 횟수.

    Returns:
        Dict[str, Any]: 성공 시 주문 결과, 실패 시 에러 정보가 담긴 딕셔너리.
    """
    try:
        # load_markets()가 미리 호출되었다고 가정합니다.
        # 필요시: if not client.markets: client.load_markets()
        market = client.market(symbol)
        step = market['precision']['amount']
        min_qty = market['limits']['amount']['min']
    except Exception as e:
        logger.error(f"심볼 '{symbol}' 정보를 가져오는 데 실패했습니다: {e}")
        return {"status": "error", "message": f"Failed to get market info for {symbol}: {e}"}

    current_qty = max(qty, min_qty)

    for attempt in range(max_retries + 1):
        try:
            params = {'reduceOnly': reduce_only}
            logger.info(f"주문 시도 ({attempt + 1}/{max_retries + 1}): {symbol} {side} {current_qty}")
            
            order = client.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=current_qty,
                params=params
            )
            logger.info(f"주문 성공: {order['id']}")
            return order

        except ccxt.InsufficientFunds as e:
            logger.warning(f"잔고 부족 오류 ({attempt + 1}/{max_retries + 1}): {e}")
            
            if attempt == max_retries:
                logger.error("최대 재시도 횟수 도달. 최종 주문 실패.")
                return {"status": "error", "message": f"Insufficient funds after {max_retries + 1} retries: {e}"}

            current_qty = _reduce_qty(current_qty, rate=0.9, min_qty=min_qty, step=step)
            
            if current_qty < min_qty:
                logger.error("수량이 최소 주문 수량보다 작아져 주문을 중단합니다.")
                return {"status": "error", "message": "Quantity fell below minimum order size after reduction."}
            
            time.sleep(0.5) # 잠시 대기 후 재시도

        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
            logger.warning(f"네트워크/거래소 오류 ({attempt + 1}/{max_retries + 1}): {e}")
            if attempt == max_retries:
                logger.error("최대 재시도 횟수 도달. 최종 주문 실패.")
                return {"status": "error", "message": f"Network/Exchange error after {max_retries + 1} retries: {e}"}
            time.sleep(1)

        except ccxt.ExchangeError as e:
            logger.error(f"거래소 오류 발생: {e}")
            return {"status": "error", "message": f"Exchange error: {e}"}
            
        except Exception as e:
            logger.error(f"예상치 못한 오류 발생: {e}", exc_info=True)
            return {"status": "error", "message": f"An unexpected error occurred: {e}"}

    return {"status": "error", "message": "Max retries reached without a successful order."}