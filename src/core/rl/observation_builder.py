# src/core/rl/observation_builder.py
# -*- coding: utf-8 -*-
"""
관측(Observation) 빌더
- market_features.extract_market_features 결과를 받아 창(window) 길이 만큼 스택
- 포지션/리스크 상태 포함하여 벡터 관측 반환
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
import numpy as np
import pandas as pd

@dataclass
class ObsConfig:
    window: int = 60
    feature_cols: Tuple[str, ...] = (
        "close","volume","ema20","ema50","rsi14","atr14","macd_line","macd_sig","macd_hist",
        "bb_low","bb_mid","bb_up","bb_width","stoch_k","stoch_d","ha_open","ha_close","ha_up",
        "volatility_30","vol_ma20","vol_spike","mom_5","mom_20","mom_60","above_sma20",
        "golden_cross_20_50","dead_cross_20_50",
    )
    # state
    include_state: bool = True

def build_obs(df: pd.DataFrame, idx: int, cfg: ObsConfig, side: int, size: float, equity: float, leverage: float) -> np.ndarray:
    """
    df: extract_market_features() 결과
    idx: 현재 인덱스(종가 시점)
    """
    start = max(0, idx - cfg.window + 1)
    win = df.iloc[start:idx+1]
    win = win[list([c for c in cfg.feature_cols if c in win.columns])]
    win = win.ffill().bfill()

    # 정규화 간단 적용: 각 특성 z-score (윈도우 기준)
    arr = win.to_numpy(dtype=np.float32)
    if arr.shape[0] > 1:
        mean = arr.mean(axis=0, keepdims=True)
        std = arr.std(axis=0, keepdims=True) + 1e-6
        arr = (arr - mean) / std
    # 패딩(앞쪽)으로 창 길이 고정
    if arr.shape[0] < cfg.window:
        pad = np.zeros((cfg.window - arr.shape[0], arr.shape[1]), dtype=np.float32)
        arr = np.concatenate([pad, arr], axis=0)

    flat = arr.flatten()
    if cfg.include_state:
        state = np.array([side, size, equity, leverage], dtype=np.float32)
        flat = np.concatenate([flat, state], axis=0)
    return flat
