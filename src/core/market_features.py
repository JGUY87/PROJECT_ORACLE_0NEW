# -*- coding: utf-8 -*-
"""
시장 피처 추출 모듈 (pandas-ta 기반 최적화)

- 목적: OHLCV 데이터로부터 안정적인 단일/다중 타임프레임 기술적 지표(피처)를 생성합니다.
- 핵심 기능:
  1) pandas-ta 통합: 신뢰성 높은 `pandas-ta` 라이브러리를 사용하여 20개 이상의 주요 지표를 계산합니다.
  2) Strategy 클래스 활용: `pandas-ta`의 `Strategy` 클래스를 사용하여 여러 지표를 한 번에 효율적으로 계산합니다.
  3) 다중 타임프레임(MTF) 지원: 여러 타임프레임의 피처를 단일 데이터프레임으로 병합하는 유틸리티를 제공합니다.
  4) 랭킹 유틸리티: 변동성, 거래량 등을 기준으로 상위 심볼을 선정하는 기능을 제공합니다.
"""
from __future__ import annotations
import logging
from typing import Dict, List

import numpy as np
import pandas as pd
import pandas_ta as ta

# --- pandas-ta 전략 정의 ---
# 계산할 모든 지표를 중앙에서 관리합니다.
LibraStrategy = ta.Strategy(
    name="Libra Core Indicators",
    description="20+ common indicators for trading bots",
    ta=[
        # 이동평균
        {"kind": "sma", "length": 20},
        {"kind": "ema", "length": 20},
        {"kind": "ema", "length": 50},
        # 오실레이터
        {"kind": "rsi", "length": 14},
        {"kind": "stoch", "k": 14, "d": 3},
        # MACD
        {"kind": "macd", "fast": 12, "slow": 26, "signal": 9},
        # 볼린저 밴드
        {"kind": "bbands", "length": 20, "std": 2},
        # 변동성
        {"kind": "atr", "length": 14},
        {"kind": "true_range", "length": 14},
        # Heikin-Ashi
        {"kind": "ha"},
        # 거래량
        {"kind": "sma", "close": "volume", "length": 20, "prefix": "vol"},
    ]
)

# --- 단일 타임프레임 피처 생성 ---
def extract_market_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    OHLCV 데이터프레임에 `pandas-ta` 전략을 적용하여 다양한 기술적 지표를 추가합니다.

    Args:
        df (pd.DataFrame): 'open', 'high', 'low', 'close', 'volume' 컬럼을 포함하고,
                           타임스탬프를 인덱스로 하는 데이터프레임.

    Returns:
        pd.DataFrame: 원본 데이터에 기술적 지표가 추가된 데이터프레임.
    """
    if df.empty:
        return pd.DataFrame()
    
    try:
        # pandas-ta 전략 적용
        df.ta.strategy(LibraStrategy)

        # --- 추가적인 커스텀 지표 계산 ---
        # 볼린저 밴드 폭
        if all(c in df.columns for c in ['BBL_20_2.0', 'BBU_20_2.0', 'BBM_20_2.0']):
            df['bb_width'] = (df['BBU_20_2.0'] - df['BBL_20_2.0']) / (df['BBM_20_2.0'] + 1e-12)

        # 거래량 스파이크
        if 'VOL_SMA_20' in df.columns:
            df['vol_spike'] = df['volume'] / (df['VOL_SMA_20'] + 1e-12)

        # Heikin-Ashi 상승/하락 추세
        if all(c in df.columns for c in ['HA_open', 'HA_close']):
            df['ha_up_trend'] = (df['HA_close'] > df['HA_open']).astype(int)

        # 골든/데드 크로스
        if all(c in df.columns for c in ['EMA_20', 'EMA_50']):
            df['golden_cross'] = ((df['EMA_20'] > df['EMA_50']) & (df['EMA_20'].shift(1) <= df['EMA_50'].shift(1))).astype(int)
            df['dead_cross'] = ((df['EMA_20'] < df['EMA_50']) & (df['EMA_20'].shift(1) >= df['EMA_50'].shift(1))).astype(int)
        
        return df.dropna()

    except Exception as e:
        logging.error(f"[피처 추출] 오류 발생: {e}", exc_info=True)
        return pd.DataFrame()

# --- 다중 타임프레임(MTF) 피처 병합 ---
_TF_SUFFIX_MAP = {"1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m", "60": "1h", "120": "2h", "240": "4h", "D": "1d"}

def _get_tf_suffix(tf: str) -> str:
    """타임프레임 문자열에 대한 표준 접미사를 반환합니다."""
    return _TF_SUFFIX_MAP.get(tf, tf.lower())

def merge_multi_timeframe_features(df_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    여러 타임프레임의 데이터프레임 딕셔너리를 입력받아, 각 피처의 마지막 행을 병합하여
    단일 행의 데이터프레임으로 반환합니다.

    Args:
        df_dict (Dict[str, pd.DataFrame]): {'타임프레임': OHLCV_데이터프레임} 형태의 딕셔너리.

    Returns:
        pd.DataFrame: 모든 타임프레임의 피처가 병합된 단일 행 데이터프레임.
    """
    try:
        feature_rows = []
        for tf, df in df_dict.items():
            features = extract_market_features(df)
            if features.empty:
                continue
            
            last_row = features.tail(1).reset_index(drop=True)
            suffix = _get_tf_suffix(tf)
            last_row_with_suffix = last_row.add_suffix(f"_{suffix}")
            feature_rows.append(last_row_with_suffix)
        
        if not feature_rows:
            return pd.DataFrame()
            
        merged_df = pd.concat(feature_rows, axis=1)
        logging.info(f"[MTF] 다중 타임프레임 피처 병합 완료. 총 컬럼 수: {merged_df.shape[1]}")
        return merged_df

    except Exception as e:
        logging.error(f"[MTF] 피처 병합 중 오류 발생: {e}", exc_info=True)
        return pd.DataFrame()

# --- 랭킹 유틸리티 ---
def get_top_ranked_symbols(
    market_data: Dict[str, pd.DataFrame],
    method: str = "volatility", 
    top_n: int = 3
) -> List[str]:
    """
    여러 심볼의 시장 데이터로부터 특정 기준(변동성, 거래량, 가격)으로 상위 N개 심볼을 선정합니다.

    Args:
        market_data (Dict[str, pd.DataFrame]): {'심볼': OHLCV_데이터프레임} 형태의 딕셔너리.
        method (str): 랭킹 기준 ('volatility', 'volume', 'price').
        top_n (int): 선정할 상위 심볼의 수.

    Returns:
        List[str]: 랭킹이 높은 순서대로 정렬된 심볼 리스트.
    """
    if not market_data:
        return []

    rankings = {}
    for symbol, df in market_data.items():
        if df.empty:
            continue
        try:
            if method == "price":
                rankings[symbol] = df['close'].iloc[-1]
            elif method == "volume":
                rankings[symbol] = df['volume'].iloc[-2:].mean() # 최근 2개 캔들 평균 거래량
            else: # volatility (기본값)
                returns = df['close'].pct_change()
                rankings[symbol] = returns.rolling(window=48, min_periods=10).std().iloc[-1]
        except (KeyError, IndexError):
            continue

    if not rankings:
        return []

    sorted_symbols = sorted(rankings.keys(), key=lambda s: rankings[s], reverse=True)
    top_symbols = sorted_symbols[:top_n]
    logging.info(f"[{method.capitalize()} 랭킹] 상위 {top_n}개 심볼: {top_symbols}")
    return top_symbols

# --- 피처 딕셔너리 변환 ---
def last_row_to_feature_dict(df: pd.DataFrame) -> Dict[str, float]:
    """
    피처 데이터프레임의 마지막 행을 AI 모델 등에 입력하기 좋은 {컬럼: 값} 딕셔너리로 변환합니다.
    NaN 값은 제외됩니다.
    """
    if df is None or df.empty:
        return {}
    row = df.tail(1).to_dict(orient="records")[0]
    return {k: float(v) for k, v in row.items() if pd.notna(v)}
