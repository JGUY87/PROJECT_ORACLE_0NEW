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

# --- 타입 힌팅 --- 
# TYPE_CHECKING 블록은 런타임 시 순환 참조를 방지하면서 타입 검사기에게만 정보를 제공합니다.
if TYPE_CHECKING:
    Exchange = ccxt.Exchange
    AsyncExchange = ccxt_async.Exchange
else:
    Exchange = Any
    AsyncExchange = Any

# --- 내부 유틸리티 함수 ---
def _quote_currency_from_symbol(symbol: str, markets: Optional[Dict[str, Any]] = None) -> str:
    """
    거래 심볼에서 기준 통화(quote currency)를 추출합니다.
    예: 'BTC/USDT' -> 'USDT', 'ETH/BTC' -> 'BTC'

    Args:
        symbol (str): 거래 심볼 (e.g., 'BTC/USDT').
        markets (Optional[Dict[str, Any]]): 미리 로드된 시장 메타데이터.

    Returns:
        str: 추출된 기준 통화.
    """
    try:
        if markets and symbol in markets:
            return markets[symbol].get('quote', '')
    except Exception:
        pass # 폴백 로직으로 진행

    # 시장 메타데이터가 없거나 실패 시 문자열 파싱으로 폴백
    if "/" in symbol:
        parts = symbol.split('/')
        quote = parts[1].split(':')[0] # 'USDT:USDT' 같은 형태 처리
        return quote
    
    # 'BTCUSDT' 같은 형태는 일반화하기 어려워 기본값으로 USDT를 가정할 수 있으나,
    # 여기서는 명시적인 포맷만 지원
    logging.warning(f"'{symbol}'에서 기준 통화를 추출할 수 없습니다. '/'가 포함된 형식을 사용하세요.")
    return symbol # 최후의 수단

# --- 동기(Sync) 잔고 조회 ---
def get_wallet_equity_sync(
    client: Exchange,
    coin: str = "USDT"
) -> Tuple[float, float, Dict[str, Any]]:
    """
    CCXT 동기 클라이언트로 특정 코인의 지갑 잔고를 조회합니다.

    Args:
        client (Exchange): 초기화된 CCXT 동기 클라이언트.
        coin (str): 잔고를 조회할 코인 (기본값: "USDT").

    Returns:
        Tuple[float, float, Dict[str, Any]]: (총 자산, 사용 가능 자산, 원본 잔고 딕셔너리).
    """
    try:
        balance = client.fetch_balance()
        total_equity = float(balance.get("total", {}).get(coin, 0.0))
        available_equity = float(balance.get("free", {}).get(coin, 0.0))
        return total_equity, available_equity, balance
    except ccxt.NetworkError as e:
        logging.error(f"[잔고 확인] 네트워크 오류: {e}")
    except ccxt.ExchangeError as e:
        logging.error(f"[잔고 확인] 거래소 오류: {e}")
    except Exception as e:
        logging.error(f"[잔고 확인] 알 수 없는 오류: {e}", exc_info=True)
    return 0.0, 0.0, {}

# --- 비동기(Async) 잔고 조회 ---
async def get_wallet_equity_async(
    client: AsyncExchange,
    coin: str = "USDT"
) -> Tuple[float, float, Dict[str, Any]]:
    """
    CCXT 비동기 클라이언트로 특정 코인의 지갑 잔고를 조회합니다.

    Args:
        client (AsyncExchange): 초기화된 CCXT 비동기 클라이언트.
        coin (str): 잔고를 조회할 코인 (기본값: "USDT").

    Returns:
        Tuple[float, float, Dict[str, Any]]: (총 자산, 사용 가능 자산, 원본 잔고 딕셔너리).
    """
    try:
        balance = await client.fetch_balance()
        total_equity = float(balance.get("total", {}).get(coin, 0.0))
        available_equity = float(balance.get("free", {}).get(coin, 0.0))
        return total_equity, available_equity, balance
    except ccxt.NetworkError as e:
        logging.error(f"[잔고 확인-비동기] 네트워크 오류: {e}")
    except ccxt.ExchangeError as e:
        logging.error(f"[잔고 확인-비동기] 거래소 오류: {e}")
    except Exception as e:
        logging.error(f"[잔고 확인-비동기] 알 수 없는 오류: {e}", exc_info=True)
    return 0.0, 0.0, {}

# --- 거래 가능 여부 판단 (동기) ---
def can_trade_sync(
    client: Exchange,
    symbol: str,
    min_notional_usdt: float = 5.0,
) -> bool:
    """
    최소 주문 금액을 기준으로 거래 가능 여부를 동기적으로 판단합니다.

    Args:
        client (Exchange): CCXT 동기 클라이언트.
        symbol (str): 거래할 심볼.
        min_notional_usdt (float): 필요한 최소 주문 가능 금액 (USDT 기준).

    Returns:
        bool: 거래 가능하면 True, 아니면 False.
    """
    try:
        markets = client.load_markets()
        quote_currency = _quote_currency_from_symbol(symbol, markets)
        _, available_equity, _ = get_wallet_equity_sync(client, quote_currency)
        return available_equity >= min_notional_usdt
    except Exception as e:
        logging.error(f"[거래 가능 확인] 오류: {e}", exc_info=True)
        return False

# --- 거래 가능 여부 판단 (비동기) ---
async def can_trade_async(
    client: AsyncExchange,
    symbol: str,
    min_notional_usdt: float = 5.0,
) -> bool:
    """
    최소 주문 금액을 기준으로 거래 가능 여부를 비동기적으로 판단합니다.

    Args:
        client (AsyncExchange): CCXT 비동기 클라이언트.
        symbol (str): 거래할 심볼.
        min_notional_usdt (float): 필요한 최소 주문 가능 금액 (USDT 기준).

    Returns:
        bool: 거래 가능하면 True, 아니면 False.
    """
    try:
        markets = await client.load_markets()
        quote_currency = _quote_currency_from_symbol(symbol, markets)
        _, available_equity, _ = await get_wallet_equity_async(client, quote_currency)
        return available_equity >= min_notional_usdt
    except Exception as e:
        logging.error(f"[거래 가능 확인-비동기] 오류: {e}", exc_info=True)
        return False