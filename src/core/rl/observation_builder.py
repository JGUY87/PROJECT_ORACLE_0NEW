# src/core/rl/observation_builder.py
# -*- coding: utf-8 -*-
"""
관측(Observation) 빌더

- market_features.extract_market_features 결과를 받아 창(window) 길이 만큼 스택합니다.
- 시장 피처와 에이전트의 현재 상태(포지션, 자산 등)를 정규화하여 최종 관측 벡터를 생성합니다.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

@dataclass
class ObsConfig:
    """관측 빌더 설정을 위한 데이터 클래스"""
    window: int = 60
    # 사용할 피처 목록을 제거하여 유연성 확보. market_features 모듈의 출력에 동적으로 대응.
    # feature_cols: Tuple[str, ...] = (...) 
    
    # 정규화 설정
    normalize_market_data: bool = True
    normalize_state_data: bool = True
    
    # 상태 정보 포함 여부
    include_state: bool = True

def _normalize_window_data(window_data: np.ndarray) -> np.ndarray:
    """
    주어진 2D 윈도우 데이터에 대해 Z-score 정규화를 적용합니다.
    
    참고: 이 방식은 각 윈도우마다 독립적으로 정규화를 수행합니다.
    이는 에이전트가 데이터의 절대적인 크기보다 윈도우 내에서의 '형태'나 '패턴'에
    더 집중하게 만드는 효과가 있으나, 전체 데이터셋의 전역적인 스케일 정보는 잃게 됩니다.
    """
    if window_data.shape[0] <= 1:
        return window_data
        
    mean = window_data.mean(axis=0, keepdims=True)
    std = window_data.std(axis=0, keepdims=True) + 1e-7 # 0으로 나누는 것을 방지
    normalized_data = (window_data - mean) / std
    return normalized_data

def _normalize_state_vector(
    side: int, size: float, equity: float, leverage: float, initial_equity: float, max_leverage: float
) -> np.ndarray:
    """에이전트의 상태 벡터를 정규화합니다."""
    return np.array([
        side,  # side는 이미 -1, 0, 1 범위이므로 그대로 사용
        size / max(1.0, initial_equity), # 포지션 크기를 초기 자본금 대비 비율로
        (equity / max(1.0, initial_equity)) - 1.0, # 자산을 초기 자본금 대비 수익률 형태로
        leverage / max(1.0, max_leverage), # 레버리지를 최대 레버리지 대비 비율로
    ], dtype=np.float32)

def build_obs(
    df_features: pd.DataFrame, 
    current_idx: int, 
    cfg: ObsConfig, 
    side: int, 
    size: float, 
    equity: float, 
    leverage: float,
    initial_equity: float,
    max_leverage: float
) -> np.ndarray:
    """
    주어진 시점(index)에 대한 최종 관측 벡터를 생성합니다.

    Args:
        df_features (pd.DataFrame): 피처가 포함된 전체 데이터프레임.
        current_idx (int): 현재 스텝의 인덱스.
        cfg (ObsConfig): 관측 빌더 설정.
        side (int): 현재 포지션 방향 (-1, 0, 1).
        size (float): 현재 포지션 크기.
        equity (float): 현재 총 자산.
        leverage (float): 현재 레버리지.
        initial_equity (float): 초기 자본금 (상태 정규화용).
        max_leverage (float): 최대 레버리지 (상태 정규화용).

    Returns:
        np.ndarray: 모델에 입력될 1차원 관측 벡터.
    """
    # 1. 시장 데이터 윈도우 슬라이싱
    start_idx = max(0, current_idx - cfg.window + 1)
    window_df = df_features.iloc[start_idx : current_idx + 1]
    
    # 누락된 값을 이전 값으로 채우고, 그래도 없으면 이후 값으로 채움
    window_df = window_df.ffill().bfill()
    
    market_obs_arr = window_df.to_numpy(dtype=np.float32)

    # 2. 시장 데이터 정규화 (선택적)
    if cfg.normalize_market_data:
        market_obs_arr = _normalize_window_data(market_obs_arr)

    # 3. 윈도우 크기에 맞게 패딩 추가
    if market_obs_arr.shape[0] < cfg.window:
        pad_width = cfg.window - market_obs_arr.shape[0]
        padding = np.zeros((pad_width, market_obs_arr.shape[1]), dtype=np.float32)
        market_obs_arr = np.concatenate([padding, market_obs_arr], axis=0)
    
    # 4. 에이전트 상태 정보 추가 (선택적)
    if not cfg.include_state:
        return market_obs_arr.flatten()

    # 5. 상태 정보 정규화 (선택적)
    if cfg.normalize_state_data:
        state_vector = _normalize_state_vector(side, size, equity, leverage, initial_equity, max_leverage)
    else:
        state_vector = np.array([side, size, equity, leverage], dtype=np.float32)
        
    # 6. 시장 관측과 상태 정보를 결합하여 최종 관측 벡터 생성
    return np.concatenate([market_obs_arr.flatten(), state_vector], axis=0)