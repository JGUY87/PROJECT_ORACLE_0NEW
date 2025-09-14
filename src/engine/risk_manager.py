# -*- coding: utf-8 -*-
"""
리스크 관리 및 주문 수량 계산을 위한 모듈.
"""
import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any

from ..core.clients import get_exchange_client

# --- 상수 정의 ---
RISK_PROFILES_PATH = Path("configs/risk_profiles.json")

def get_risk_profile(profile_name: str = 'balanced') -> Optional[Dict[str, Any]]:
    """
    설정 파일에서 지정된 리스크 프로필을 로드합니다.
    """
    try:
        with open(RISK_PROFILES_PATH, 'r', encoding='utf-8') as f:
            profiles = json.load(f)
        return profiles.get(profile_name)
    except FileNotFoundError:
        logging.error(f"리스크 프로필 파일을 찾을 수 없습니다: {RISK_PROFILES_PATH}")
        return None
    except json.JSONDecodeError:
        logging.error(f"리스크 프로필 파일의 형식이 잘못되었습니다: {RISK_PROFILES_PATH}")
        return None

async def get_account_balance(coin: str = 'USDT') -> float:
    """
    거래소에서 특정 코인의 사용 가능한 잔고를 조회합니다.
    """
    client = None
    try:
        client = get_exchange_client()
        balance = await client.fetch_balance()
        return float(balance.get(coin, {}).get('free', 0.0))
    except Exception as e:
        logging.error(f"계좌 잔고 조회 실패: {e}", exc_info=True)
        return 0.0
    finally:
        if client:
            await client.close()

async def get_current_price(symbol: str) -> float:
    """
    거래소에서 현재가(ticker)를 조회합니다.
    """
    client = None
    try:
        client = get_exchange_client()
        ticker = await client.fetch_ticker(symbol)
        return float(ticker['last'])
    except Exception as e:
        logging.error(f"현재가 조회 실패: {e}", exc_info=True)
        return 0.0
    finally:
        if client:
            await client.close()

async def calculate_order_size(
    symbol: str, 
    side: str,
    risk_profile_name: str = 'balanced', 
    stop_loss_pct: float = 0.02
) -> Optional[float]:
    """
    리스크 관리 원칙에 따라 주문 수량을 계산합니다.

    Args:
        symbol (str): 주문할 심볼.
        side (str): 'buy' 또는 'sell'.
        risk_profile_name (str): 사용할 리스크 프로필 이름.
        stop_loss_pct (float): 손절매 비율 (e.g., 0.02 for 2%).

    Returns:
        Optional[float]: 계산된 주문 수량, 실패 시 None.
    """
    # 1. 리스크 프로필 로드
    profile = get_risk_profile(risk_profile_name)
    if not profile:
        logging.error("주문 수량 계산 실패: 리스크 프로필을 로드할 수 없습니다.")
        return None

    per_trade_risk_pct = profile.get('per_trade_risk_pct')
    if not per_trade_risk_pct:
        logging.error("주문 수량 계산 실패: 'per_trade_risk_pct'가 프로필에 없습니다.")
        return None

    # 2. 계좌 잔고 및 현재가 조회
    balance = await get_account_balance()
    current_price = await get_current_price(symbol)

    if balance <= 0 or current_price <= 0:
        logging.error("주문 수량 계산 실패: 잔고 또는 현재가 정보를 가져올 수 없습니다.")
        return None

    # 3. 리스크 금액 및 손절 가격 계산
    risk_amount_per_trade = balance * per_trade_risk_pct
    
    if side == 'buy':
        stop_loss_price = current_price * (1 - stop_loss_pct)
        price_diff = current_price - stop_loss_price
    elif side == 'sell':
        stop_loss_price = current_price * (1 + stop_loss_pct)
        price_diff = stop_loss_price - current_price
    else:
        logging.error(f"잘못된 주문 방향입니다: {side}")
        return None

    if price_diff <= 0:
        logging.warning("손절 가격과 현재 가격의 차이가 없어 수량을 계산할 수 없습니다.")
        return None

    # 4. 주문 수량 계산
    order_size = risk_amount_per_trade / price_diff
    
    # TODO: 최소 주문 수량, 수량 단위 등 거래소 제약사항에 맞춰 수량 조정 필요
    # 예: round(order_size, 3)
    
    logging.info(
        f"주문 수량 계산 완료: "
        f"잔고=${balance:,.2f}, "
        f"리스크비율={per_trade_risk_pct:.2%}, "
        f"리스크금액=${risk_amount_per_trade:,.2f}, "
        f"현재가=${current_price:,.2f}, "
        f"손절가=${stop_loss_price:,.2f}, "
        f"계산된수량={order_size:.4f}"
    )
    
    return order_size


async def get_account_summary() -> Optional[Dict[str, Any]]:
    """
    계좌의 요약 정보를 조회합니다 (총 자산, 사용 가능, 총 미실현 손익).
    """
    client = None
    try:
        client = get_exchange_client()
        
        # Bybit v5 통합계정(UNIFIED) 잔고 조회
        balance_info = await client.fetch_balance(params={'accountType': 'UNIFIED'})
        
        total_equity = balance_info.get('total', {}).get('equity')
        available_balance = balance_info.get('total', {}).get('free')
        total_pnl = balance_info.get('total', {}).get('unrealizedPnl')

        # 포지션 정보 조회
        positions = await client.fetch_positions(params={'category': 'linear'})
        open_positions = [
            {
                "symbol": p['info']['symbol'],
                "side": p['side'],
                "size": p['contracts'],
                "entryPrice": p['entryPrice'],
                "markPrice": p['markPrice'],
                "pnl": p['unrealizedPnl'],
            }
            for p in positions if p.get('contracts') and float(p['contracts']) > 0
        ]

        summary = {
            "total_equity": float(total_equity or 0.0),
            "available_balance": float(available_balance or 0.0),
            "total_pnl": float(total_pnl or 0.0),
            "open_positions": open_positions,
        }
        logging.info(f"계좌 요약 정보 조회 완료: {summary}")
        return summary

    except Exception as e:
        logging.error(f"계좌 요약 정보 조회 실패: {e}", exc_info=True)
        return None
    finally:
        if client:
            await client.close()
