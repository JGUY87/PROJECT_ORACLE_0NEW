# -*- coding: utf-8 -*-
"""
CCXT를 사용하여 거래소 레버리지 설정 및 확인
"""
import ccxt
import logging

async def ensure_leverage(client: ccxt.Exchange, symbol: str, desired_leverage: int):
    """
    지정된 심볼의 레버리지를 확인하고 필요시 설정합니다.

    Args:
        client (ccxt.Exchange): CCXT 거래소 클라이언트 객체.
        symbol (str): 거래 심볼 (예: 'BTC/USDT:USDT').
        desired_leverage (int): 설정할 레버리지 값.
    """
    try:
        # 단일 심볼의 포지션 정보를 직접 가져옵니다.
        position = await client.fetch_position(symbol)

        # 포지션이 없는 경우, 레버리지를 설정할 수 없으므로 건너뜁니다.
        if not position or not position.get('leverage'):
            logging.info(f"[LEVERAGE] {symbol}: 현재 포지션 없음. 레버리지 설정 건너뜀.")
            return

        current_leverage = int(position.get("leverage", 0))

        # 현재 레버리지가 원하는 값과 다를 경우에만 설정합니다.
        if current_leverage != desired_leverage:
            logging.info(f"[LEVERAGE] {symbol}: 현재 레버리지({current_leverage}x) -> 목표 레버리지({desired_leverage}x)로 변경 시도...")
            await client.set_leverage(desired_leverage, symbol)
            logging.info(f"[LEVERAGE] {symbol}: 레버리지 {desired_leverage}x 설정 완료.")
        else:
            logging.info(f"[LEVERAGE] {symbol}: 레버리지가 이미 {desired_leverage}x으로 설정되어 있습니다.")

    except ccxt.ExchangeError as e:
        # 거래소에서 레버리지 설정을 지원하지 않거나, 다른 API 관련 오류 발생 시
        logging.error(f"[LEVERAGE] {symbol} 레버리지 설정 중 거래소 오류 발생: {e}")
    except Exception as e:
        # 네트워크 문제 등 예상치 못한 오류 처리
        logging.exception(f"[LEVERAGE] {symbol} 레버리지 설정 중 예상치 못한 오류 발생: {e}")