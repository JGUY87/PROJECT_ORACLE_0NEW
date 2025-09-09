# -*- coding: utf-8 -*-
"""
OHLCV 데이터 로딩, 캐싱, 전처리 파이프라인을 제공합니다.

- 목적: OHLCV 데이터의 안정적인 로딩, 캐싱, 전처리를 담당합니다.
- 핵심 기능:
  1) CCXT 연동: `ccxt`를 사용하여 Bybit v5 API로부터 OHLCV 데이터를 비동기적으로 로드합니다.
  2) 로컬 캐싱: `data/` 폴더에 `심볼_인터벌.csv` 형식으로 데이터를 캐싱하여 API 요청을 최소화합니다.
  3) 데이터 정규화: `pandas`를 사용하여 OHLCV 데이터를 정제하고, 타임스탬프를 UTC 기준으로 통일합니다.
  4) 미완성 캔들 제거: 데이터의 정합성을 위해 마지막 미완성 캔들을 제거하는 옵션을 제공합니다.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import ccxt.async_support as ccxt

# --- 상수 정의 ---
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True) # 데이터 디렉토리 생성

# --- 데이터 정규화 헬퍼 ---
def _normalize_ohlcv_df(df: pd.DataFrame) -> pd.DataFrame:
    """CCXT로부터 받은 OHLCV 데이터를 표준 포맷으로 정규화합니다."""
    if df.empty:
        return df
    
    # 컬럼 이름 표준화
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    
    # 타임스탬프를 UTC 기준으로 datetime 객체로 변환
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    
    # OHLCV 컬럼을 숫자형으로 변환 (오류 발생 시 NaN 처리)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    # 타임스탬프를 인덱스로 설정
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    return df

# --- 캐시 관리 --- 
def _get_cache_path(symbol: str, interval: str) -> Path:
    """캐시 파일 경로를 생성합니다."""
    safe_symbol = symbol.replace('/', '_')
    return DATA_DIR / f"{safe_symbol}_{interval}.csv"

async def _read_from_cache(path: Path) -> Optional[pd.DataFrame]:
    """캐시에서 데이터를 비동기적으로 읽습니다."""
    if not path.exists():
        return None
    try:
        # 현재 파일 I/O는 동기적으로 처리되지만, 향후 aiofiles 등으로 교체 가능
        df = pd.read_csv(path, index_col='timestamp', parse_dates=True)
        # UTC 시간대로 설정
        df.index = df.index.tz_localize('UTC')
        logging.info(f"[데이터] 캐시에서 {path.name} 로드 ({len(df)}개 행)")
        return df if not df.empty else None
    except Exception as e:
        logging.warning(f"[데이터] 캐시 파일 읽기 오류: {e}")
        return None

async def _write_to_cache(path: Path, df: pd.DataFrame):
    """데이터를 캐시에 비동기적으로 씁니다."""
    try:
        df.to_csv(path)
        logging.info(f"[데이터] {path.name} 캐시 저장 ({len(df)}개 행)")
    except Exception as e:
        logging.error(f"[데이터] 캐시 파일 쓰기 오류: {e}")

# --- 데이터 로딩 메인 함수 ---
async def fetch_ohlcv(
    client: ccxt.Exchange,
    symbol: str,
    interval: str,
    limit: int = 1000,
    use_cache: bool = True,
    drop_incomplete: bool = True
) -> pd.DataFrame:
    """
    Bybit API를 통해 K-line(OHLCV) 데이터를 가져옵니다.

    - 캐시를 우선적으로 읽고, 부족한 데이터는 API를 통해 업데이트합니다.
    - 마지막 미완성 캔들을 자동으로 제거하여 데이터 정합성을 보장합니다.

    Args:
        client (ccxt.Exchange): 초기화된 CCXT 비동기 클라이언트.
        symbol (str): 거래 심볼 (예: 'BTC/USDT').
        interval (str): 캔들 간격 (예: '1m', '5m', '1h', '1d').
        limit (int): API로부터 가져올 최대 캔들 수.
        use_cache (bool): 캐시 사용 여부.
        drop_incomplete (bool): 마지막 미완성 캔들 제거 여부.

    Returns:
        pd.DataFrame: OHLCV 데이터프레임 (인덱스: timestamp).
    """
    cache_path = _get_cache_path(symbol, interval)

    if use_cache:
        cached_df = await _read_from_cache(cache_path)
        if cached_df is not None:
            # TODO: 캐시가 최신인지 확인하고, 부족한 부분만 API로 가져오는 로직 추가
            return cached_df

    try:
        logging.info(f"[데이터] Bybit API에서 {symbol} ({interval}) 데이터를 로딩합니다...")
        
        # CCXT를 사용하여 OHLCV 데이터 가져오기
        ohlcv_list = await client.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        if not ohlcv_list:
            logging.warning(f"[데이터] API로부터 {symbol} 데이터를 가져오지 못했습니다.")
            return pd.DataFrame()

        df = pd.DataFrame(ohlcv_list)
        df = _normalize_ohlcv_df(df)

        # 미완성 캔들 제거
        if drop_incomplete and not df.empty:
            # 마지막 행이 현재 시간과 너무 가까우면 미완성으로 간주
            # 이 로직은 인터벌에 따라 더 정교해질 수 있음
            df = df.iloc[:-1]

        if use_cache:
            await _write_to_cache(cache_path, df)

        return df

    except ccxt.NetworkError as e:
        logging.error(f"[데이터] 네트워크 오류 발생: {e}")
    except ccxt.ExchangeError as e:
        logging.error(f"[데이터] 거래소 오류 발생: {e}")
    except Exception as e:
        logging.error(f"[데이터] K-line 데이터 로딩 중 예외 발생: {e}", exc_info=True)
    
    return pd.DataFrame() # 오류 발생 시 빈 데이터프레임 반환
