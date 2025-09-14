# -*- coding: utf-8 -*-
"""
OHLCV 데이터 로딩, 캐싱, 전처리 파이프라인을 제공합니다.

- 목적: OHLCV 데이터의 안정적인 로딩, 증분 캐싱, 전처리를 담당합니다.
- 핵심 기능:
  1) CCXT 연동: `ccxt`를 사용하여 Bybit v5 API로부터 OHLCV 데이터를 비동기적으로 로드합니다.
  2) 증분 캐싱: `data/` 폴더에 데이터를 캐싱하고, 마지막 데이터 이후의 최신 데이터만 API로 가져와 업데이트합니다.
  3) 데이터 정규화: `pandas`를 사용하여 OHLCV 데이터를 정제하고, 타임스탬프를 UTC 기준으로 통일합니다.
  4) 미완성 캔들 제거: 데이터의 정합성을 위해 마지막 미완성 캔들을 정확히 식별하여 제거합니다.
"""
from __future__ import annotations
import logging
import asyncio
from pathlib import Path
from typing import Optional

import pandas as pd
import ccxt.async_support as ccxt

# --- 상수 정의 ---
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
logger = logging.getLogger(__name__)

# --- 헬퍼 함수 ---
def _interval_to_timedelta(interval: str) -> pd.Timedelta:
    """'1m', '5m', '1h', '1d' 같은 인터벌 문자열을 Timedelta 객체로 변환합니다."""
    return pd.to_timedelta(interval)

def _normalize_ohlcv_df(df: pd.DataFrame) -> pd.DataFrame:
    """CCXT로부터 받은 OHLCV 리스트를 표준 포맷의 데이터프레임으로 정규화합니다."""
    if df.empty:
        return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume']).set_index(pd.to_datetime([]))
    
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    df.set_index('timestamp', inplace=True)
    df.sort_index(inplace=True)
    return df

# --- 캐시 관리 ---
def _get_cache_path(symbol: str, interval: str) -> Path:
    """캐시 파일 경로를 생성합니다."""
    safe_symbol = symbol.replace('/', '_').replace(':', '_')
    return DATA_DIR / f"{safe_symbol}_{interval}.csv"

async def _read_from_cache(path: Path) -> Optional[pd.DataFrame]:
    """캐시에서 데이터를 비동기적으로 읽습니다."""
    if not path.exists():
        return None
    try:
        # 동기 I/O를 별도 스레드에서 실행하여 이벤트 루프 차단 방지
        df = await asyncio.to_thread(pd.read_csv, path, index_col='timestamp', parse_dates=True)
        df.index = df.index.tz_convert('UTC') # 시간대를 UTC로 통일
        logger.info(f"[데이터] 캐시에서 {path.name} 로드 ({len(df)}개 행)")
        return df if not df.empty else None
    except Exception as e:
        logger.warning(f"[데이터] 캐시 파일 읽기 오류: {e}")
        return None

async def _write_to_cache(path: Path, df: pd.DataFrame):
    """데이터를 캐시에 비동기적으로 씁니다."""
    try:
        # 동기 I/O를 별도 스레드에서 실행
        await asyncio.to_thread(df.to_csv, path)
        logger.info(f"[데이터] {path.name} 캐시 저장 ({len(df)}개 행)")
    except Exception as e:
        logger.error(f"[데이터] 캐시 파일 쓰기 오류: {e}")

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
    - 캐시를 우선적으로 읽고, 부족한 데이터는 API를 통해 증분 업데이트합니다.
    - 마지막 미완성 캔들을 자동으로 제거하여 데이터 정합성을 보장합니다.
    """
    cache_path = _get_cache_path(symbol, interval)
    since = None
    cached_df = None

    if use_cache:
        cached_df = await _read_from_cache(cache_path)
        if cached_df is not None and not cached_df.empty:
            last_timestamp = cached_df.index[-1]
            since = int(last_timestamp.timestamp() * 1000)
            logger.info(f"[데이터] 캐시 발견. {last_timestamp} 이후 데이터부터 증분 로딩합니다.")

    try:
        logger.info(f"[데이터] Bybit API에서 {symbol} ({interval}) 데이터를 로딩합니다 (Since: {since})...")
        
        ohlcv_list = await client.fetch_ohlcv(symbol, timeframe=interval, limit=limit, since=since)
        
        if not ohlcv_list:
            logger.info("[데이터] API로부터 새로운 데이터를 가져오지 못했습니다. 캐시된 데이터를 반환합니다.")
            return cached_df if cached_df is not None else pd.DataFrame()

        new_df = _normalize_ohlcv_df(pd.DataFrame(ohlcv_list))

        # 캐시 데이터와 새로운 데이터 병합
        if cached_df is not None:
            df = pd.concat([cached_df, new_df])
            # 중복된 인덱스(타임스탬프)는 최신 데이터로 유지
            df = df[~df.index.duplicated(keep='last')]
            df.sort_index(inplace=True)
        else:
            df = new_df

        # 미완성 캔들 제거 로직 개선
        if drop_incomplete and not df.empty:
            last_time = df.index[-1]
            interval_td = _interval_to_timedelta(interval)
            # 마지막 캔들의 예상 종료 시간이 현재보다 미래이면 미완성으로 간주
            if last_time + interval_td > pd.Timestamp.utcnow():
                df = df.iloc[:-1]
                logger.info("[데이터] 마지막 미완성 캔들 1개를 제거했습니다.")

        if use_cache and not df.empty:
            await _write_to_cache(cache_path, df)

        return df

    except (ccxt.NetworkError, ccxt.ExchangeError) as e:
        logger.error(f"[데이터] CCXT 오류 발생: {e}")
    except Exception as e:
        logger.error(f"[데이터] K-line 데이터 로딩 중 예외 발생: {e}", exc_info=True)
    
    # 오류 발생 시 캐시된 데이터가 있으면 그것이라도 반환
    return cached_df if cached_df is not None else pd.DataFrame()