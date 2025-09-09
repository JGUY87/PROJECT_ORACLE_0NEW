# -*- coding: utf-8 -*-
"""
Bybit v5 API 클라이언트 중앙 관리 모듈 (CCXT 기반)

- 목적: Bybit v5 API의 비동기 클라이언트를 중앙에서 관리하고, 일관된 방식으로 제공합니다.
- 핵심:
  1) 비동기 클라이언트: `ccxt.async_support`를 사용하여 비동기 HTTP 클라이언트를 관리합니다.
  2) 싱글턴 패턴: 애플리케이션 전체에서 단일 클라이언트 인스턴스를 사용하도록 보장합니다.
  3) 중앙화된 인증: `src.config.utils`를 통해 API 키를 안전하게 로드합니다.
"""
from __future__ import annotations
import logging
from typing import Optional, Dict, Any

import ccxt.async_support as ccxt

from ..config.utils import get_api_keys
from ..config.config_loader import load_all_configs

# --- 싱글턴 인스턴스 --- 
_client_instance: Optional[ccxt.Exchange] = None

# --- 클라이언트 관리 --- 
async def get_bybit_client() -> ccxt.Exchange:
    """
    Bybit v5 비동기 클라이언트의 싱글턴 인스턴스를 반환합니다.
    인스턴스가 없으면 새로 생성하고, 있으면 기존 인스턴스를 반환합니다.

    Returns:
        ccxt.Exchange: 초기화된 Bybit 비동기 클라이언트.

    Raises:
        ValueError: API 키를 찾을 수 없을 때 발생합니다.
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    logging.info("[Bybit 클라이언트] 새로운 Bybit 클라이언트 인스턴스를 생성합니다...")
    
    # 설정 및 API 키 로드
    configs = load_all_configs()
    api_key, api_secret = get_api_keys("bybit")

    if not api_key or not api_secret:
        logging.error("[Bybit 클라이언트] Bybit API 키를 찾을 수 없습니다. 설정 파일을 확인하세요.")
        raise ValueError("Bybit API 키가 설정되지 않았습니다.")

    is_testnet = configs.settings.get("is_testnet", False)

    try:
        client = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future', # 선물 거래를 기본으로 설정
                'adjustForTimeDifference': True, # 서버 시간 동기화
            },
        })
        
        if is_testnet:
            client.set_sandbox_mode(True)
            logging.info("[Bybit 클라이언트] 테스트넷 모드로 설정되었습니다.")

        # 연결 테스트
        await client.fetch_time()
        logging.info(f"[Bybit 클라이언트] 클라이언트 생성 및 서버 연결 성공 (테스트넷: {is_testnet})")
        
        _client_instance = client
        return _client_instance

    except Exception as e:
        logging.error(f"[Bybit 클라이언트] 클라이언트 생성에 실패했습니다: {e}", exc_info=True)
        # 클라이언트 생성 실패 시, 인스턴스를 None으로 유지
        _client_instance = None 
        raise e # 오류를 다시 발생시켜 상위 호출자에게 알림

async def close_bybit_client():
    """
    생성된 Bybit 클라이언트의 연결을 종료합니다.
    애플리케이션 종료 시 호출해야 합니다.
    """
    global _client_instance
    if _client_instance is not None:
        logging.info("[Bybit 클라이언트] Bybit 클라이언트 연결을 종료합니다...")
        await _client_instance.close()
        _client_instance = None

# ======================= 사용 예시 =======================
async def main():
    """클라이언트 생성 및 기본 API 호출 예시입니다."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    try:
        # 클라이언트 가져오기
        client = await get_bybit_client()
        
        # API 호출 예시: USDT 선물 잔고 조회
        balance = await client.fetch_balance(params={"accountType": "UNIFIED", "coin": "USDT"})
        print("\n--- USDT 잔고 정보 ---")
        print(balance.get('USDT'))

        # API 호출 예시: BTC/USDT Ticker 정보 조회
        ticker = await client.fetch_ticker('BTC/USDT:USDT')
        print("\n--- BTC/USDT Ticker 정보 ---")
        print(ticker)

    except Exception as e:
        print(f"\n오류 발생: {e}")
    finally:
        # 클라이언트 연결 종료
        await close_bybit_client()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
