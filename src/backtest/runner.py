# -*- coding: utf-8 -*-
"""VectorBT를 사용한 백테스팅 실행기 (v2 - 데이터 캐싱 추가)."""
import logging
from pathlib import Path
import pandas as pd
import vectorbt as vbt
from typing import Tuple, Optional

from ..core.bybit_router import get_bybit_client

# --- 상수 정의 ---
OUTPUT_DIR = Path("outputs/backtests")
CACHE_DIR = Path("data/cache")


async def get_ohlcv_data(symbol: str, start_date: str, end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    OHLCV 데이터를 가져옵니다. 로컬 캐시를 우선 확인하고, 없으면 거래소에서 다운로드합니다.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_symbol = symbol.replace('/', '_')
    
    # 캐시 파일 이름에 end_date를 포함시켜 더 유연한 캐싱 지원
    year_str = start_date.split('-')[0]
    end_year_str = end_date.split('-')[0] if end_date else year_str
    cache_filename = f"{safe_symbol}_1d_{year_str}_{end_year_str}.csv"
    cache_filepath = CACHE_DIR / cache_filename

    if cache_filepath.exists():
        logging.info(f"캐시된 데이터 '{cache_filepath}'를 사용합니다.")
        df = pd.read_csv(cache_filepath, index_col='timestamp', parse_dates=True)
        
        # 요청된 기간에 맞게 데이터 필터링
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date) if end_date else pd.Timestamp.now()
        return df[(df.index >= start_dt) & (df.index <= end_dt)]

    logging.info(f"캐시된 데이터 없음. {symbol}의 일봉 OHLCV 데이터를 거래소에서 가져옵니다...")
    client = None
    try:
        client = await get_bybit_client()
        since = client.parse8601(f"{start_date}T00:00:00Z")
        
        # end_date가 있으면 해당 날짜까지만 데이터를 가져오도록 시도
        # (주의: fetch_ohlcv는 since 기반이므로, 후처리에서 end_date를 잘라내야 함)
        ohlcv = await client.fetch_ohlcv(symbol, '1d', since=since, limit=2000)
        
        if not ohlcv:
            logging.error(f"{symbol}에 대한 OHLCV 데이터를 가져올 수 없습니다.")
            return None

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # 전체 다운로드된 데이터를 캐싱
        full_cache_filename = f"{safe_symbol}_1d_{year_str}_full.csv"
        full_cache_filepath = CACHE_DIR / full_cache_filename
        logging.info(f"전체 데이터를 '{full_cache_filepath}' 파일에 캐싱합니다.")
        df.to_csv(full_cache_filepath)
        
        # 요청된 기간에 맞게 데이터 필터링하여 반환
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date) if end_date else pd.Timestamp.now()
        filtered_df = df[(df.index >= start_dt) & (df.index <= end_dt)]
        
        # 기간이 명시된 경우, 해당 기간에 대한 별도 캐시 저장
        if end_date:
            logging.info(f"기간이 명시된 데이터를 '{cache_filepath}' 파일에 캐싱합니다.")
            filtered_df.to_csv(cache_filepath)
            
        return filtered_df
    except Exception as e:
        logging.error(f"OHLCV 데이터 가져오기 실패: {e}", exc_info=True)
        return None
    finally:
        if client:
            await client.close()


async def run_ma_crossover_backtest(
    symbol: str, 
    start_date: str, 
    end_date: Optional[str] = None,
    fast_ma: int = 10, 
    slow_ma: int = 30
) -> Tuple[Optional[pd.Series], Optional[Path], Optional[Path]]:
    """
    이동평균 교차 전략에 대한 백테스트를 실행하고 결과를 저장합니다.
    """
    logging.info(f"{symbol}에 대한 백테스트를 시작합니다 (기간: {start_date} ~ {end_date or '최신'})...")
    
    try:
        # 1. 데이터 가져오기 (캐싱 로직 내장)
        df = await get_ohlcv_data(symbol, start_date, end_date)
        
        if df is None or df.empty:
            logging.error("데이터를 가져오지 못해 백테스트를 중단합니다.")
            return None, None, None
            
        price = df['close']

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
        
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        safe_symbol = symbol.replace('/', '_')
        end_date_str = end_date.replace('-', '') if end_date else 'latest'
        filename_base = f"{safe_symbol}_{start_date.replace('-', '')}_{end_date_str}_MA_{fast_ma}_{slow_ma}"
        stats_path = OUTPUT_DIR / f"{filename_base}_stats.txt"
        plot_path = OUTPUT_DIR / f"{filename_base}_plot.html"

        logging.info(f"백테스트 통계를 '{stats_path}' 파일에 저장합니다...")
        with open(stats_path, 'w', encoding='utf-8') as f:
            f.write(str(stats))

        logging.info(f"백테스트 시각화 결과를 '{plot_path}' 파일에 저장합니다...")
        fig = pf.plot()
        fig.write_html(str(plot_path))
        
        logging.info(f"백테스트 완료. 결과가 {stats_path} 및 {plot_path}에 저장되었습니다.")
        return stats, stats_path, plot_path

    except Exception as e:
        logging.error(f"백테스트 중 오류 발생: {e}", exc_info=True)
        return None, None, None
    finally:
        # 클라이언트 연결 종료 로직은 get_ohlcv_data 함수 내부로 이동
        pass
