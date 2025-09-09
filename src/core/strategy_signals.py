# -*- coding: utf-8 -*-
"""
📈 src/core/strategy_signals.py — EMA+RSI fallback (pandas-ta 통합)
- 🛠️ pandas-ta를 사용하여 EMA 및 RSI 계산 로직 최적화
"""
from __future__ import annotations
from typing import Dict, Literal, Any
import pandas as pd
import pandas_ta as ta  # 📦 pandas-ta 라이브러리 임포트

Side = Literal['BUY','SELL','HOLD']

def generate_signal(df: pd.DataFrame, strategy: str = "ema_rsi_fallback", **kwargs: Any) -> Dict[str, Any]:
    """
    🧮 주어진 데이터프레임과 전략에 따라 거래 신호를 생성합니다.
    Args:
        df (pd.DataFrame): 시세 데이터 (close 가격 포함).
        strategy (str): 사용할 전략 이름 (현재는 'ema_rsi_fallback'만 지원).
        **kwargs: 전략에 전달할 추가 인자.
    Returns:
        Dict[str, Any]: 생성된 신호 (signal, confidence).
    """
    if strategy == "ema_rsi_fallback":
        return ema_rsi_fallback(df, **kwargs)
    # 📌 향후 다른 전략 추가 가능
    return {'signal':'HOLD','confidence':0.0}

def ema_rsi_fallback(
    df: pd.DataFrame,
    fast:int=9,
    slow:int=21,
    rsi_len:int=14,
    rsi_buy:float=55.0,
    rsi_sell:float=45.0,
    min_slope:float=0.0
) -> Dict[str, Any]:
    """
    ⚡ EMA와 RSI를 활용한 폴백 전략.
    Args:
        df (pd.DataFrame): 시세 데이터 (close 가격 포함).
        fast (int): 빠른 EMA 기간.
        slow (int): 느린 EMA 기간.
        rsi_len (int): RSI 기간.
        rsi_buy (float): RSI 매수 기준값.
        rsi_sell (float): RSI 매도 기준값.
        min_slope (float): EMA 기울기 최소값.
    Returns:
        Dict[str, Any]: 생성된 신호 (signal, confidence).
    """
    n = len(df)
    if n < max(fast, slow, rsi_len) + 3:  # ⏸️ 충분한 데이터가 없으면 HOLD
        return {'signal':'HOLD','confidence':0.0}

    # 📊 pandas-ta를 사용하여 EMA 계산
    df['ema_fast'] = ta.ema(df['close'], length=fast)
    df['ema_slow'] = ta.ema(df['close'], length=slow)

    # 📊 pandas-ta를 사용하여 RSI 계산
    df['rsi'] = ta.rsi(df['close'], length=rsi_len)

    # 📌 최신 EMA 값
    ema_fast, ema_slow = df['ema_fast'].iloc[-1], df['ema_slow'].iloc[-1]
    prev_fast, prev_slow = df['ema_fast'].iloc[-2], df['ema_slow'].iloc[-2]
    rsival = df['rsi'].iloc[-1]

    # 📈 EMA 기울기 계산
    slope = (ema_fast - prev_fast) / max(prev_fast, 1e-12) if prev_fast != 0 else 0.0

    # 🟢 매수 조건: 골든 크로스 발생, RSI 매수 기준 이상, EMA 기울기 양수
    if prev_fast <= prev_slow and ema_fast > ema_slow and rsival >= rsi_buy and slope >= min_slope:
        return {'signal':'BUY','confidence':0.7}
    # 🔴 매도 조건: 데드 크로스 발생, RSI 매도 기준 이하, EMA 기울기 음수
    if prev_fast >= prev_slow and ema_fast < ema_slow and rsival <= rsi_sell and (-slope) >= min_slope:
        return {'signal':'SELL','confidence':0.7}

    return {'signal':'HOLD','confidence':0.0}

# 🔗 이전 버전과의 호환성을 위한 별칭
ema_fallback = ema_rsi_fallback
