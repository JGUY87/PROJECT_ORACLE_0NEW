# -*- coding: utf-8 -*-
"""VectorBT를 사용한 백테스팅 실행기."""
import logging
import os
from pathlib import Path
import pandas as pd
import vectorbt as vbt
from typing import Tuple, Optional

from ..core.clients import get_exchange_client

# --- 상수 정의 ---
# 결과물을 저장할 기본 디렉토리
OUTPUT_DIR = Path("outputs/backtests")

async def run_ma_crossover_backtest(
    symbol: str, 
    start_date: str, 
    fast_ma: int = 10, 
    slow_ma: int = 30
) -> Tuple[Optional[pd.Series], Optional[Path]]:
    """
    이동평균 교차 전략에 대한 백테스트를 실행하고 결과를 저장합니다.

    Args:
        symbol (str): 백테스트할 심볼 (예: 'BTC/USDT')
        start_date (str): 데이터 시작 날짜 (예: '2023-01-01')
        fast_ma (int): 단기 이동평균선 기간
        slow_ma (int): 장기 이동평균선 기간

    Returns:
        Tuple[Optional[pd.Series], Optional[Path]]: 백테스트 통계와 결과 파일 경로.
    """
    logging.info(f"{symbol}에 대한 백테스트를 시작합니다 (시작일: {start_date})...")
    
    client = None
    try:
        # 1. 데이터 가져오기
        logging.info("거래소 클라이언트를 초기화합니다...")
        client = get_exchange_client()
        since = client.parse8601(f'{start_date}T00:00:00Z')
        
        logging.info(f"{symbol}의 일봉 OHLCV 데이터를 가져옵니다...")
        ohlcv = await client.fetch_ohlcv(symbol, '1d', since=since, limit=2000) # 데이터 양을 늘려 안정성 확보
        
        if not ohlcv:
            logging.error(f"{symbol}에 대한 OHLCV 데이터를 가져올 수 없습니다. 백테스트를 중단합니다.")
            return None, None

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        price = df.set_index('timestamp')['close']

        # 2. 진입/청산 신호 생성 (vectorbt 형식)
        logging.info(f"이동평균(MA) 지표 및 교차 신호를 계산합니다 (단기: {fast_ma}, 장기: {slow_ma})...")
        fast_ma_series = vbt.MA.run(price, fast_ma)
        slow_ma_series = vbt.MA.run(price, slow_ma)
        
        entries = fast_ma_series.ma_crossed_above(slow_ma_series)
        exits = fast_ma_series.ma_crossed_below(slow_ma_series)

        # 3. 포트폴리오 시뮬레이션 실행
        logging.info("포트폴리오 시뮬레이션을 실행합니다...")
        pf = vbt.Portfolio.from_signals(
            price, 
            entries, 
            exits, 
            init_cash=10000, # 초기 자본금
            freq='1D' # 데이터 빈도
        )

        # 4. 결과 저장
        stats = pf.stats()
        
        # 출력 디렉토리 생성
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        # 안전한 파일명 생성
        safe_symbol = symbol.replace('/', '_')
        filename_base = f"{safe_symbol}_{start_date}_MA_{fast_ma}_{slow_ma}"
        stats_path = OUTPUT_DIR / f"{filename_base}_stats.txt"

        logging.info(f"백테스트 통계를 '{stats_path}' 파일에 저장합니다...")
        with open(stats_path, 'w', encoding='utf-8') as f:
            f.write(str(stats))
        
        logging.info(f"백테스트 완료. 결과가 {stats_path}에 저장되었습니다.")
        return stats, stats_path

    except Exception as e:
        logging.error(f"백테스트 중 오류 발생: {e}", exc_info=True)
        return None, None # 오류 발생 시 None 반환
    finally:
        if client:
            logging.info("거래소 클라이언트 연결을 종료합니다.")
            await client.close()