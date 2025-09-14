# -*- coding: utf-8 -*-
"""
src/core/balance_guard.py

- 최소 잔고 확인을 통해 거래 가능 여부를 판단합니다.
- CCXT를 사용하여 동기/비동기 방식으로 지갑 잔고를 조회하는 유틸리티를 제공합니다.
"""
from __future__ import annotations
import logging
from typing import Dict, Any, Tuple, Optional, TYPE_CHECKING

import ccxt
import ccxt.async_support as ccxt_async

# 로거 설정
logger = logging.getLogger(__name__)

# --- 타입 힌팅 ---
if TYPE_CHECKING:
    Exchange = ccxt.Exchange
    AsyncExchange = ccxt_async.Exchange
else:
    Exchange = Any
    AsyncExchange = Any

# --- 내부 유틸리티 함수 ---
def _get_quote_currency(symbol: str, markets: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    거래 심볼에서 기준 통화(quote currency)를 추출합니다.
    예: 'BTC/USDT' -> 'USDT', 'ETH/BTC' -> 'BTC'

    Args:
        symbol (str): 거래 심볼 (e.g., 'BTC/USDT').
        markets (Optional[Dict[str, Any]]): 미리 로드된 시장 메타데이터.

    Returns:
        Optional[str]: 추출된 기준 통화. 실패 시 None.
    """
    try:
        if markets and symbol in markets:
            return markets[symbol].get('quote')
    except Exception as e:
        logger.warning(f"Markets 딕셔너리에서 '{symbol}' 조회 중 오류: {e}")

    # 시장 메타데이터가 없거나 실패 시 문자열 파싱으로 폴백
    if "/" in symbol:
        parts = symbol.split('/')
        quote = parts[1].split(':')[0]  # 'USDT:USDT' 같은 형태 처리
        return quote
    
    logger.error(f"'{symbol}'에서 기준 통화를 추출할 수 없습니다. 'BASE/QUOTE' 형식을 사용하세요.")
    return None

# --- 동기(Sync) 잔고 조회 ---
def get_wallet_equity_sync(
    client: Exchange,
    coin: str
) -> Tuple[float, float, Dict[str, Any]]:
    """
    CCXT 동기 클라이언트로 특정 코인의 지갑 잔고를 조회합니다.

    Args:
        client (Exchange): 초기화된 CCXT 동기 클라이언트.
        coin (str): 잔고를 조회할 코인.

    Returns:
        Tuple[float, float, Dict[str, Any]]: (총 자산, 사용 가능 자산, 원본 잔고 딕셔너리).
    """
    try:
        balance = client.fetch_balance()
        # .get(coin, 0.0)을 사용하여 해당 코인 잔고가 없는 경우 0.0을 반환
        total_equity = float(balance.get("total", {}).get(coin, 0.0))
        available_equity = float(balance.get("free", {}).get(coin, 0.0))
        return total_equity, available_equity, balance
    except (ccxt.NetworkError, ccxt.ExchangeError) as e:
        logger.error(f"[잔고 확인] CCXT 오류: {e}")
    except Exception as e:
        logger.error(f"[잔고 확인] 알 수 없는 오류: {e}", exc_info=True)
    return 0.0, 0.0, {}

# --- 비동기(Async) 잔고 조회 ---
async def get_wallet_equity_async(
    client: AsyncExchange,
    coin: str
) -> Tuple[float, float, Dict[str, Any]]:
    """
    CCXT 비동기 클라이언트로 특정 코인의 지갑 잔고를 조회합니다.

    Args:
        client (AsyncExchange): 초기화된 CCXT 비동기 클라이언트.
        coin (str): 잔고를 조회할 코인.

    Returns:
        Tuple[float, float, Dict[str, Any]]: (총 자산, 사용 가능 자산, 원본 잔고 딕셔너리).
    """
    try:
        balance = await client.fetch_balance()
        total_equity = float(balance.get("total", {}).get(coin, 0.0))
        available_equity = float(balance.get("free", {}).get(coin, 0.0))
        return total_equity, available_equity, balance
    except (ccxt.NetworkError, ccxt.ExchangeError) as e:
        logger.error(f"[잔고 확인-비동기] CCXT 오류: {e}")
    except Exception as e:
        logger.error(f"[잔고 확인-비동기] 알 수 없는 오류: {e}", exc_info=True)
    return 0.0, 0.0, {}

# --- 거래 가능 여부 판단 (동기) ---
def can_trade_sync(
    client: Exchange,
    symbol: str,
    min_balance_threshold: float = 5.0,
) -> bool:
    """
    최소 잔고를 기준으로 거래 가능 여부를 동기적으로 판단합니다.

    Args:
        client (Exchange): CCXT 동기 클라이언트.
        symbol (str): 거래할 심볼.
        min_balance_threshold (float): 필요한 최소 주문 가능 금액 (Quote Currency 기준).

    Returns:
        bool: 거래 가능하면 True, 아니면 False.
    """
    try:
        # client.markets가 로드되었는지 확인, 아니면 로드
        if not client.markets:
            logger.info("Markets 정보가 로드되지 않았습니다. 새로 로드합니다.")
            client.load_markets()
            
        quote_currency = _get_quote_currency(symbol, client.markets)
        if not quote_currency:
            return False # 기준 통화 추출 실패 시 거래 불가

        _, available_equity, _ = get_wallet_equity_sync(client, quote_currency)
        
        logger.info(f"[{symbol}] 사용 가능 잔고: {available_equity:.2f} {quote_currency}, 필요 최소 잔고: {min_balance_threshold:.2f} {quote_currency}")
        return available_equity >= min_balance_threshold
    except Exception as e:
        logger.error(f"[거래 가능 확인] 오류: {e}", exc_info=True)
        return False

# --- 거래 가능 여부 판단 (비동기) ---
async def can_trade_async(
    client: AsyncExchange,
    symbol: str,
    min_balance_threshold: float = 5.0,
) -> bool:
    """
    최소 잔고를 기준으로 거래 가능 여부를 비동기적으로 판단합니다.

    Args:
        client (AsyncExchange): CCXT 비동기 클라이언트.
        symbol (str): 거래할 심볼.
        min_balance_threshold (float): 필요한 최소 주문 가능 금액 (Quote Currency 기준).

    Returns:
        bool: 거래 가능하면 True, 아니면 False.
    """
    try:
        if not client.markets:
            logger.info("Markets 정보가 로드되지 않았습니다. 새로 로드합니다. (비동기)")
            await client.load_markets()

        quote_currency = _get_quote_currency(symbol, client.markets)
        if not quote_currency:
            return False

        _, available_equity, _ = await get_wallet_equity_async(client, quote_currency)
        
        logger.info(f"[{symbol}] 사용 가능 잔고: {available_equity:.2f} {quote_currency}, 필요 최소 잔고: {min_balance_threshold:.2f} {quote_currency}")
        return available_equity >= min_balance_threshold
    except Exception as e:
        logger.error(f"[거래 가능 확인-비동기] 오류: {e}", exc_info=True)
        return False
