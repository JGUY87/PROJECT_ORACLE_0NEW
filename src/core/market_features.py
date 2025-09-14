# -*- coding: utf-8 -*-
"""
시장 피처 추출 모듈 (pandas-ta 기반 최적화)

- 목적: OHLCV 데이터로부터 안정적인 단일/다중 타임프레임 기술적 지표(피처)를 생성합니다.
- 핵심 기능:
  1) pandas-ta 통합: 신뢰성 높은 `pandas-ta` 라이브러리를 사용하여 20개 이상의 주요 지표를 계산합니다.
  2) 동적 피처 계산: 하드코딩된 컬럼 이름 대신, 동적으로 생성된 피처 이름을 참조하여 유지보수성을 높입니다.
  3) 다중 타임프레임(MTF) 지원: 여러 타임프레임의 피처를 단일 데이터프레임으로 효율적으로 병합합니다.
  4) 랭킹 유틸리티: 변동성, 거래량 등을 기준으로 상위 심볼을 선정하는 기능을 제공합니다.
"""
from __future__ import annotations
import logging
from typing import Dict, List

import numpy as np
import pandas as pd
import pandas_ta as ta

# Now, we can safely use pandas_ta
logger = logging.getLogger(__name__)

# --- pandas-ta 전략 정의 ---
LibraStrategy = ta.Strategy(
    name="Libra Core Indicators",
    description="20+ common indicators for trading bots",
    ta=[
        {"kind": "sma", "length": 20},
        {"kind": "ema", "length": 20},
        {"kind": "ema", "length": 50},
        {"kind": "rsi", "length": 14},
        {"kind": "stoch", "k": 14, "d": 3},
        {"kind": "macd", "fast": 12, "slow": 26, "signal": 9},
        {"kind": "bbands", "length": 20, "std": 2},
        {"kind": "atr", "length": 14},
        {"kind": "true_range", "length": 14},
        {"kind": "ha"},
        {"kind": "sma", "close": "volume", "length": 20, "prefix": "vol"},
    ]
)

# --- 커스텀 피처 계산 헬퍼 ---
def _add_bollinger_features(df: pd.DataFrame) -> pd.DataFrame:
    """볼린저 밴드 관련 커스텀 피처를 추가합니다."""
    bb_upper_col = df.filter(like='BBU_').columns[0]
    bb_lower_col = df.filter(like='BBL_').columns[0]
    bb_mid_col = df.filter(like='BBM_').columns[0]
    if all(c in df.columns for c in [bb_upper_col, bb_lower_col, bb_mid_col]):
        df['bb_width'] = (df[bb_upper_col] - df[bb_lower_col]) / (df[bb_mid_col] + 1e-12)
    return df

def _add_volume_features(df: pd.DataFrame) -> pd.DataFrame:
    """거래량 관련 커스텀 피처를 추가합니다."""
    vol_sma_cols = df.filter(like='VOL_SMA_').columns
    if len(vol_sma_cols) > 0:
        vol_sma_col = vol_sma_cols[0]
        if vol_sma_col in df.columns and 'volume' in df.columns:
            df['vol_spike'] = df['volume'] / (df[vol_sma_col] + 1e-12)
    return df

def _add_trend_features(df: pd.DataFrame) -> pd.DataFrame:
    """추세 관련 커스텀 피처(Heikin-Ashi, Cross)를 추가합니다."""
    if all(c in df.columns for c in ['HA_open', 'HA_close']):
        df['ha_up_trend'] = (df['HA_close'] > df['HA_open']).astype(int)
    
    ema_short_col = df.filter(regex='EMA_20').columns[0]
    ema_long_col = df.filter(regex='EMA_50').columns[0]
    if all(c in df.columns for c in [ema_short_col, ema_long_col]):
        df['golden_cross'] = ((df[ema_short_col] > df[ema_long_col]) & (df[ema_short_col].shift(1) <= df[ema_long_col].shift(1))).astype(int)
        df['dead_cross'] = ((df[ema_short_col] < df[ema_long_col]) & (df[ema_short_col].shift(1) >= df[ema_long_col].shift(1))).astype(int)
    return df

# --- Bybit 데이터 로더 ---
def get_bybit_data(symbol: str, interval: str, limit: int = 1000) -> pd.DataFrame:
    """Bybit v5 API를 사용하여 OHLCV 데이터를 가져옵니다."""
    try:
        # Bybit API는 밀리초 타임스탬프를 사용합니다.
        # 이 예제에서는 ccxt와 같은 라이브러리를 사용한다고 가정합니다.
        # 실제 구현에서는 API 클라이언트 초기화가 필요합니다.
        # 여기서는 임시로 bybit 객체를 생성합니다.
        import ccxt
        bybit = ccxt.bybit({
            'options': {
                'defaultType': 'swap',
                'adjustForTimeDifference': True,
            },
        })
        
        # v5 API는 'category' 파라미터가 필요합니다.
        params = {'category': 'linear'}
        
        # timeframe 포맷 변환 (예: "1" -> "1m")
        timeframe = _TF_SUFFIX_MAP.get(interval, interval)
        
        # 데이터 로드
        ohlcv = bybit.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit, params=params)
        
        if not ohlcv:
            logger.warning(f"[{symbol}] {interval} 데이터 로드 실패. 빈 데이터를 반환합니다.")
            return pd.DataFrame()

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        logger.info(f"[{symbol}] {interval} 데이터 {len(df)}개 행 로드 완료.")
        return df

    except Exception as e:
        logger.error(f"[{symbol}] Bybit 데이터 로드 중 심각한 오류 발생: {e}", exc_info=True)
        return pd.DataFrame()


# --- 단일 타임프레임 피처 생성 ---
def extract_market_features(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV 데이터프레임에 `pandas-ta` 전략과 커스텀 지표를 적용합니다."""
    # Child process에서 importlib.metadata를 찾지 못하는 문제 해결
    import importlib.metadata
    
    if df.empty:
        return pd.DataFrame()
    
    try:
        df.ta.study(LibraStrategy, append=True)
        
        df = _add_bollinger_features(df)
        df = _add_volume_features(df)
        df = _add_trend_features(df)
        
        # 모델 호환성을 위해 불필요한 Heikin-Ashi 컬럼 제거
        ha_cols_to_drop = ['HA_open', 'HA_high', 'HA_low', 'HA_close']
        df.drop(columns=[col for col in ha_cols_to_drop if col in df.columns], inplace=True)
        
        return df.dropna()
    except Exception as e:
        logger.error(f"[피처 추출] 오류 발생: {e}", exc_info=True)
        return pd.DataFrame()

# --- 다중 타임프레임(MTF) 피처 병합 ---
_TF_SUFFIX_MAP = {"1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m", "60": "1h", "120": "2h", "240": "4h", "D": "1d"}

def combine_mtf_features(feature_df_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    각 타임프레임별로 '피처가 이미 계산된' 데이터프레임을 받아, 마지막 행을 병합하여
    단일 행의 데이터프레임으로 반환합니다.
    """
    try:
        feature_rows = []
        for tf, df in feature_df_dict.items():
            if df.empty:
                continue
            
            last_row = df.tail(1).reset_index(drop=True)
            suffix = _TF_SUFFIX_MAP.get(tf, tf.lower())
            last_row_with_suffix = last_row.add_suffix(f"_{suffix}")
            feature_rows.append(last_row_with_suffix)
        
        if not feature_rows:
            return pd.DataFrame()
            
        merged_df = pd.concat(feature_rows, axis=1)
        logger.info(f"[MTF] 다중 타임프레임 피처 병합 완료. 총 컬럼 수: {merged_df.shape[1]}")
        return merged_df
    except Exception as e:
        logger.error(f"[MTF] 피처 병합 중 오류 발생: {e}", exc_info=True)
        return pd.DataFrame()

# --- 랭킹 유틸리티 ---
def get_top_ranked_symbols(
    market_data: Dict[str, pd.DataFrame],
    method: str = "volatility", 
    top_n: int = 3,
    volatility_window: int = 48
) -> List[str]:
    """
    여러 심볼의 시장 데이터로부터 특정 기준(변동성, 거래량, 가격)으로 상위 N개 심볼을 선정합니다.
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
                rankings[symbol] = df['volume'].iloc[-2:].mean()
            else: # volatility (기본값)
                returns = df['close'].pct_change()
                rankings[symbol] = returns.rolling(window=volatility_window, min_periods=10).std().iloc[-1]
        except (KeyError, IndexError) as e:
            logger.warning(f"'{symbol}' 심볼 랭킹 계산 중 오류: {e}")
            continue

    if not rankings:
        return []

    sorted_symbols = sorted(rankings.keys(), key=lambda s: rankings.get(s, -np.inf), reverse=True)
    top_symbols = sorted_symbols[:top_n]
    logger.info(f"[{method.capitalize()} 랭킹] 상위 {top_n}개 심볼: {top_symbols}")
    return top_symbols

# --- 피처 딕셔너리 변환 ---
def last_row_to_feature_dict(df: pd.DataFrame) -> Dict[str, float]:
    """피처 데이터프레임의 마지막 행을 {컬럼: 값} 딕셔너리로 변환합니다."""
    if df is None or df.empty:
        return {}
    row = df.iloc[-1].to_dict()
    return {k: float(v) for k, v in row.items() if pd.notna(v)}

def get_longest_indicator_period(strategy_name: str = "default") -> int:
    """
    LibraStrategy에 정의된 지표들 중 가장 긴 기간(period)을 찾아 반환합니다.
    """
    # 현재는 strategy_name에 따라 다른 전략을 로드하는 로직이 없으므로,
    # 인자는 받지만 사용하지 않고 LibraStrategy를 기준으로 계산합니다.
    # 추후 다른 전략이 추가되면 이 부분을 확장할 수 있습니다.
    longest = 0
    for indicator in LibraStrategy.ta:
        if "length" in indicator:
            longest = max(longest, indicator["length"])
        if "slow" in indicator:
            longest = max(longest, indicator["slow"])
        if "fast" in indicator:
            longest = max(longest, indicator["fast"])
    return longest