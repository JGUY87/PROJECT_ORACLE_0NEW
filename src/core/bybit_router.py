# -*- coding: utf-8 -*-
"""
Bybit v5 API 클라이언트 중앙 관리 모듈 (CCXT 기반)

- 목적: Bybit v5 API의 비동기 클라이언트를 중앙에서 관리하고, 일관된 방식으로 제공합니다.
- 핵심:
  1) 비동기 클라이언트: `ccxt.async_support`를 사용하여 비동기 HTTP 클라이언트를 관리합니다.
  2) 안정적인 싱글턴: `asyncio.Lock`을 사용하여 비동기 환경에서도 단일 클라이언트 인스턴스를 보장합니다.
  3) 중앙화된 인증: `src.config`를 통해 API 키와 설정을 안전하게 로드합니다.
"""
from __future__ import annotations
import logging
import asyncio
from typing import Optional

import ccxt.async_support as ccxt

from ..config.utils import get_api_keys
from ..config.config_loader import load_all_configs

# --- 싱글턴 인스턴스 및 비동기 잠금 ---
_client_instance: Optional[ccxt.Exchange] = None
_client_lock = asyncio.Lock()

# --- 클라이언트 관리 ---
async def get_bybit_client() -> ccxt.Exchange:
    """
    Bybit v5 비동기 클라이언트의 싱글턴 인스턴스를 안전하게 반환합니다.
    인스턴스가 없으면 새로 생성하고, 있으면 기존 인스턴스를 반환합니다.

    Returns:
        ccxt.Exchange: 초기화된 Bybit 비동기 클라이언트.

    Raises:
        ValueError: API 키를 찾을 수 없을 때 발생합니다.
        ccxt.BaseError: 클라이언트 생성 또는 연결 테스트에 실패했을 때 발생합니다.
    """
    global _client_instance
    # 빠른 경로: 인스턴스가 이미 존재하면 잠금 없이 즉시 반환
    if _client_instance is not None:
        return _client_instance

    # 인스턴스가 없을 경우, 잠금을 획득하여 한 번에 하나만 생성하도록 보장
    async with _client_lock:
        # 잠금을 기다리는 동안 다른 작업이 인스턴스를 생성했을 수 있으므로 다시 확인
        if _client_instance is not None:
            return _client_instance

        logging.info("[Bybit 클라이언트] 새로운 Bybit 클라이언트 인스턴스를 생성합니다...")
        
        # 설정(settings.ini) 및 API 키(api_keys.ini) 로드
        configs = load_all_configs()
        api_key, api_secret = get_api_keys("bybit")

        if not api_key or not api_secret:
            logging.error("[Bybit 클라이언트] Bybit API 키를 찾을 수 없습니다. 'conf/api_keys.ini' 파일을 확인하세요.")
            raise ValueError("Bybit API 키가 설정되지 않았습니다.")

        is_testnet = configs.settings.get("is_testnet", False)

        try:
            client = ccxt.bybit({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',  # 'future' 대신 'swap' 사용 (USDT 무기한 선물)
                    'adjustForTimeDifference': True,
                },
            })
            
            if is_testnet:
                client.set_sandbox_mode(True)
                logging.info("[Bybit 클라이언트] 테스트넷 모드로 설정되었습니다.")

            # 연결 테스트
            await client.fetch_time()
            logging.info(f"[Bybit 클라이언트] 클라이언트 생성 및 서버 연결 성공 (Testnet: {is_testnet})")
            
            # 전역 변수에 인스턴스 할당
            _client_instance = client
            return _client_instance

        except Exception as e:
            logging.error(f"[Bybit 클라이언트] 클라이언트 생성에 실패했습니다: {e}", exc_info=True)
            raise e

async def close_bybit_client():
    """
    생성된 Bybit 클라이언트의 연결을 종료하고 인스턴스를 정리합니다.
    애플리케이션 종료 시 호출해야 합니다.
    """
    global _client_instance
    if _client_instance is not None:
        async with _client_lock:
            # 잠금 내에서 다시 확인
            if _client_instance is not None:
                logging.info("[Bybit 클라이언트] Bybit 클라이언트 연결을 종료합니다...")
                await _client_instance.close()
                _client_instance = None
                logging.info("[Bybit 클라이언트] 클라이언트 연결이 성공적으로 종료되었습니다.")

# ======================= 사용 예시 =======================
async def main():
    """클라이언트 생성 및 기본 API 호출 예시입니다."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    client = None
    try:
        # 클라이언트 가져오기
        client = await get_bybit_client()
        
        # API 호출 예시: USDT 선물 잔고 조회
        balance = await client.fetch_balance(params={"accountType": "UNIFIED", "coin": "USDT"})
        print("\n--- USDT 잔고 정보 ---")
        # 사용 가능한 잔고와 전체 잔고 출력
        usdt_balance = balance.get('USDT', {{}})
        print(f"Free: {usdt_balance.get('free')}, Total: {usdt_balance.get('total')}")

        # API 호출 예시: BTC/USDT Ticker 정보 조회
        ticker = await client.fetch_ticker('BTC/USDT:USDT')
        print("\n--- BTC/USDT Ticker 정보 ---")
        print(f"Last Price: {ticker.get('last')}, Bid: {ticker.get('bid')}, Ask: {ticker.get('ask')}")

    except Exception as e:
        print(f"\n오류 발생: {e}")
    finally:
        # 클라이언트 연결 종료
        if client:
            await close_bybit_client()

if __name__ == "__main__":
    asyncio.run(main())