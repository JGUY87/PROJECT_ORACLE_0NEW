# -*- coding: utf-8 -*-
"""거래 주문 실행을 위한 헬퍼 함수들."""
import logging
from typing import Optional, Dict, Any
from ..core.clients import get_exchange_client

async def place_market_order(symbol: str, side: str, amount: float) -> Optional[Dict[str, Any]]:
    """
    시장가 주문을 실행하고 결과를 반환합니다.

    Args:
        symbol (str): 주문할 심볼 (e.g., 'BTC/USDT')
        side (str): 'buy' 또는 'sell'
        amount (float): 주문할 수량

    Returns:
        Optional[Dict[str, Any]]: 성공 시 주문 결과 딕셔너리, 실패 시 None
    """
    client = None
    try:
        client = get_exchange_client()
        logging.info(f"시장가 주문 실행: {symbol}, 방향: {side}, 수량: {amount}")
        
        # Bybit API v5에 맞는 파라미터 설정
        params = {
            'category': 'linear',  # 선물 거래
            'accountType': 'UNIFIED' # 통합 계정
        }
        
        order = await client.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=amount,
            params=params
        )
        
        logging.info(f"주문 성공: {order}")
        return order
        
    except Exception as e:
        logging.error(f"시장가 주문 실패: {e}", exc_info=True)
        return None
    finally:
        if client:
            await client.close()

async def get_open_positions(symbol: str) -> list:
    """
    특정 심볼에 대한 현재 오픈 포지션을 가져옵니다.
    """
    client = None
    try:
        client = get_exchange_client()
        params = {'category': 'linear', 'symbol': symbol}
        positions = await client.fetch_positions(symbols=[symbol], params=params)
        
        # 실제 포지션이 있는 경우만 필터링
        open_positions = [p for p in positions if p.get('size') and float(p['size']) != 0]
        return open_positions
        
    except Exception as e:
        logging.error(f"포지션 정보 조회 실패: {e}", exc_info=True)
        return []
    finally:
        if client:
            await client.close()
