# -*- coding: utf-8 -*-
"""
주문 실행을 위한 비동기 헬퍼 함수 모음.

이 모듈의 함수들은 초기화된 CCXT 클라이언트 객체를 인자로 받아, 
거래소에 실제 주문을 전송하는 역할을 합니다.
"""
import logging
from typing import Dict, Any
import ccxt.async_support as ccxt

async def place_market_order(
    client: ccxt.Exchange,
    symbol: str, 
    side: str, 
    qty: float, 
    params: Dict[str, Any] = {}
) -> Dict[str, Any]:
    """
    시장가 주문을 실행하는 공통 함수입니다.

    Args:
        client (ccxt.Exchange): 초기화된 CCXT 비동기 클라이언트.
        symbol (str): 주문할 심볼 (예: 'BTC/USDT').
        side (str): 주문 사이드 ('buy' 또는 'sell').
        qty (float): 주문 수량.
        params (dict): 거래소에 전달할 추가 파라미터 (예: {'reduceOnly': True}).

    Returns:
        dict: 거래소로부터 받은 주문 결과 딕셔너리.

    Raises:
        ccxt.NetworkError: 네트워크 관련 오류 발생 시.
        ccxt.ExchangeError: 거래소 API 오류 발생 시.
    """
    try:
        logging.info(f"[{symbol}] 시장가 주문 실행: {side} {qty}개, 파라미터: {params}")
        
        # CCXT의 통합된 주문 생성 메소드 사용
        order = await client.create_order(
            symbol=symbol, 
            type='market', 
            side=side, 
            amount=qty, 
            params=params
        )

        logging.info(f"[{symbol}] 주문 성공. 주문 ID: {order.get('id')}")
        return order

    except ccxt.NetworkError as e:
        logging.error(f"[{symbol}] 주문 실패 (네트워크 오류): {e}")
        raise  # 오류를 다시 발생시켜 상위 로직에서 처리하도록 함
    except ccxt.ExchangeError as e:
        logging.error(f"[{symbol}] 주문 실패 (거래소 오류): {e}")
        raise
    except Exception as e:
        logging.error(f"[{symbol}] 주문 실패 (알 수 없는 오류): {e}", exc_info=True)
        raise

async def close_position(
    client: ccxt.Exchange,
    symbol: str, 
    position_side: str, 
    qty: float
) -> Dict[str, Any]:
    """
    지정된 포지션을 시장가로 종료합니다.

    Args:
        client (ccxt.Exchange): CCXT 비동기 클라이언트.
        symbol (str): 종료할 포지션의 심볼.
        position_side (str): 종료할 포지션의 사이드 ('long' 또는 'short').
        qty (float): 종료할 수량.

    Returns:
        dict: 거래소로부터 받은 청산 주문 결과.
    """
    # 롱 포지션 종료는 'sell', 숏 포지션 종료는 'buy' 주문
    close_side = 'sell' if position_side.lower() == 'long' else 'buy'
    
    logging.info(f"[{symbol}] 포지션 종료 주문 실행. 사이드: {position_side}, 수량: {qty}")
    
    # reduceOnly 파라미터를 사용하여 포지션 감소만 가능하도록 보장
    return await place_market_order(client, symbol, close_side, qty, params={'reduceOnly': True})
