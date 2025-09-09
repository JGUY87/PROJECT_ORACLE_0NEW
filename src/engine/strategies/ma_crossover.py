# -*- coding: utf-8 -*-
"""
이동평균선 교차(MA Crossover) 전략
"""
import pandas as pd
import logging

def check_signal(df: pd.DataFrame, fast_period: int = 10, slow_period: int = 30):
    """
    DataFrame을 받아 이동평균선 교차 신호를 확인합니다.

    Args:
        df (pd.DataFrame): 'close' 컬럼을 포함하는 OHLCV 데이터프레임
        fast_period (int): 단기 이동평균선 기간
        slow_period (int): 장기 이동평균선 기간

    Returns:
        str: 'buy', 'sell', 또는 'hold'
    """
    if df.empty or len(df) < slow_period:
        return 'hold'

    # pandas-ta를 사용하여 이동평균선 계산
    # append=True를 통해 df에 직접 컬럼을 추가합니다.
    df.ta.sma(length=fast_period, append=True)
    df.ta.sma(length=slow_period, append=True)

    # 컬럼 이름 확인 (pandas-ta 기본 형식: SMA_10, SMA_30)
    fast_ma_col = f'SMA_{fast_period}'
    slow_ma_col = f'SMA_{slow_period}'
    
    if fast_ma_col not in df.columns or slow_ma_col not in df.columns:
        logging.error(f"Could not find MA columns: {fast_ma_col}, {slow_ma_col}")
        return 'hold'

    # 마지막 두 개의 데이터 포인트(캔들) 가져오기
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    logging.debug(f"Checking signal: Fast MA={last_row[fast_ma_col]:.4f}, Slow MA={last_row[slow_ma_col]:.4f}")

    # 골든 크로스 (매수 신호)
    if prev_row[fast_ma_col] < prev_row[slow_ma_col] and last_row[fast_ma_col] > last_row[slow_ma_col]:
        logging.info(f"Golden Cross (BUY signal) detected for {df.name}")
        return 'buy'
    
    # 데드 크로스 (매도 신호)
    elif prev_row[fast_ma_col] > prev_row[slow_ma_col] and last_row[fast_ma_col] < last_row[slow_ma_col]:
        logging.info(f"Dead Cross (SELL signal) detected for {df.name}")
        return 'sell'
        
    return 'hold'
