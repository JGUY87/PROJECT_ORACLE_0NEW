# -*- coding: utf-8 -*-
"""core/strategy_recommender.py — v2.0 Config-driven Logic
모든 전략/액션 임계값을 `configs/strategy_params.json`에서 로드하여 유연성 확보.
"""
from __future__ import annotations
import os
import json
from typing import Any, Dict, Tuple
import numpy as np
import pandas as pd

# --- 전역 설정 및 레이블 ---
try:
    _config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'configs', 'strategy_params.json')
    with open(_config_path, 'r', encoding='utf-8') as f:
        PARAMS = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Warning: Cannot load strategy_params.json. Using default fallbacks. Error: {e}")
    PARAMS = {}

PRIMARY_TIMEFRAME = PARAMS.get("primary_timeframe", "1m")
STRATEGY_THRESHOLDS = PARAMS.get("strategy_thresholds", {})
ACTION_THRESHOLDS = PARAMS.get("action_thresholds", {})

LABELS = {
    "hukwoonyam": "강화학습 PPO",
    "wonyotti": "워뇨띠",
    "td_mark": "탐드마크",
    "volume_pullback": "거래량 눌림목",
    "smart_money_accumulation": "매집",
    "bollinger_breakout": "볼린저 밴드 돌파",
    "snake_ma": "EMA 폴백",
    "ppo": "PPO",
}
FEATURE_ORDER = ["ma_20", "volatility", "rsi", "disparity", "momentum", "stoch_k", "golden_cross", "dead_cross", "ppo_score", "is_downtrend", "pullback_detected", "box_range", "support_accumulation"]

# --- 유틸리티 함수 ---
def _is_num(x):
    try:
        float(x)
        return True
    except (ValueError, TypeError):
        return False

def as_features(obj) -> Dict[str, float]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return {str(k): float(v) if _is_num(v) else v for k, v in obj.items()}
    
    s = None
    if isinstance(obj, pd.Series):
        s = obj
    elif isinstance(obj, pd.DataFrame):
        if len(obj) == 0:
            return {}
        s = obj.iloc[-1]

    if s is not None:
        return {str(k): float(v) if _is_num(v) else v for k, v in s.items()}
    
    if isinstance(obj, (list, tuple, np.ndarray)):
        arr = np.asarray(obj).astype(float)
        arr = arr[0] if arr.ndim == 2 and arr.shape[0] == 1 else arr
        N = min(len(arr), len(FEATURE_ORDER))
        return {FEATURE_ORDER[i]: float(arr[i]) for i in range(N)}
    
    return {}

# --- 핵심 로직: 전략 및 액션 선택 ---
def choose_strategy(f: Dict[str, float]) -> Tuple[str, str, int]:
    # 지표 추출
    ppo = f.get("ppo_score", 0.0)
    is_down = bool(f.get("is_downtrend", False))
    volsp = f.get("vol_spike", 1.0)
    rsi = f.get("rsi", 50.0)
    td = int(f.get("td_reversal", 0))
    pull = bool(f.get("pullback_detected", False))
    box = bool(f.get("box_range", False))
    acc = f.get("support_accumulation", 0.0)

    # --- 1. 볼린저 밴드 돌파 (최우선 순위) ---
    p_bb = STRATEGY_THRESHOLDS.get("bollinger_breakout", {})
    if p_bb.get("enabled", False):
        # 피처 이름에서 볼린저 밴드 컬럼 동적 찾기
        bbu_col = next((c for c in f if c.startswith('BBU_')), None)
        bbl_col = next((c for c in f if c.startswith('BBL_')), None)
        
        if bbu_col and bbl_col:
            close = f.get("close", 0.0)
            bbu = f.get(bbu_col, float('inf'))
            bbl = f.get(bbl_col, float('-inf'))
            
            if close > bbu:
                return "bollinger_breakout", "상단 밴드 돌파", 11
            if close < bbl:
                return "bollinger_breakout", "하단 밴드 돌파", 11

    # --- 2. 기존 전략들 ---
    p = STRATEGY_THRESHOLDS
    if ppo > p.get("hukwoonyam", {}).get("ppo_score", 0.80):
        return "hukwoonyam", "PPO 강화", 10
    elif is_down and volsp > p.get("wonyotti", {}).get("vol_spike", 1.3) and rsi < p.get("wonyotti", {}).get("rsi", 30):
        return "wonyotti", "하락+과매도+거래량급등", 9
    elif volsp > p.get("volume_pullback", {}).get("vol_spike", 1.5) and pull:
        return "volume_pullback", "거래량 눌림목", 8
    elif td == p.get("td_mark", {}).get("td_reversal", 1):
        return "td_mark", "TD 반전", 7
    elif box and acc >= p.get("smart_money_accumulation", {}).get("support_accumulation", 3):
        return "smart_money_accumulation", "매집", 6
    else:
        return "snake_ma", "EMA 폴백", 5

def choose_action(f: Dict[str, float]) -> Tuple[str, float]:
    # 지표 추출
    golden = int(f.get("golden_cross", 0))
    dead = int(f.get("dead_cross", 0))
    mom = float(f.get("momentum", 0.0))
    rsi = float(f.get("rsi", 50.0))
    stoch = float(f.get("stoch_k", 50.0))
    is_down = bool(f.get("is_downtrend", False))
    # MACD 히스토그램 값 동적 찾기
    macdh_col = next((c for c in f if c.startswith('MACDh_')), None)
    macdh = float(f.get(macdh_col, 0.0)) if macdh_col else 0.0

    # 설정에서 임계값 가져오기
    p_hold = ACTION_THRESHOLDS.get("hold_conditions", {})
    p_score = ACTION_THRESHOLDS.get("scoring", {})
    p_dec = ACTION_THRESHOLDS.get("decision", {})
    p_ind = ACTION_THRESHOLDS.get("indicators", {})

    # 중립(HOLD) 조건
    if (golden == 0 and dead == 0) and \
       abs(mom) <= p_hold.get("momentum_abs", 1e-3) and \
       p_hold.get("rsi_min", 45) <= rsi <= p_hold.get("rsi_max", 55) and \
       p_hold.get("stoch_min", 30) <= stoch <= p_hold.get("stoch_max", 70):
        return "hold", 0.0

    # 점수 계산
    buy_score = 0
    buy_score += p_score.get("buy_golden_cross", 2) if golden == 1 else 0
    buy_score += p_score.get("buy_momentum_positive", 1) if mom > 0 else 0
    buy_score += p_score.get("buy_rsi_low", 1) if rsi < p_ind.get("rsi_buy", 35) else 0
    buy_score += p_score.get("buy_stoch_low", 1) if stoch < p_ind.get("stoch_buy", 20) else 0
    buy_score += p_score.get("buy_not_downtrend", 1) if not is_down else 0
    buy_score += p_score.get("buy_macd_histogram_positive", 1) if macdh > 0 else 0

    sell_score = 0
    sell_score += p_score.get("sell_dead_cross", 2) if dead == 1 else 0
    sell_score += p_score.get("sell_momentum_negative", 1) if mom < 0 else 0
    sell_score += p_score.get("sell_rsi_high", 1) if rsi > p_ind.get("rsi_sell", 65) else 0
    sell_score += p_score.get("sell_stoch_high", 1) if stoch > p_ind.get("stoch_sell", 80) else 0
    sell_score += p_score.get("sell_is_downtrend", 1) if is_down else 0
    sell_score += p_score.get("sell_macd_histogram_negative", 1) if macdh < 0 else 0

    # 최종 결정
    min_score = p_dec.get("min_score_for_action", 2)
    min_diff = p_dec.get("min_score_difference", 2)
    
    if max(buy_score, sell_score) < min_score or abs(buy_score - sell_score) < min_diff:
        return "hold", 0.0

    if sell_score > buy_score:
        return "sell", min(1.0, sell_score / 6.0)
    else:
        return "buy", min(1.0, buy_score / 6.0)

# --- 메인 진입점 ---
def ai_recommend_strategy_live(*args, **kwargs) -> Dict[str, Any]:
    symbol = kwargs.pop("symbol", "UNKNOWN")
    features = kwargs.pop("features", None) or kwargs.pop("multi_feats", None) or (args[0] if (len(args) == 1 and not isinstance(args[0], str)) else None)
    
    f = as_features(features)

    if not f:
        # 여러 심볼에 대한 피처가 딕셔너리로 들어온 경우
        if len(args) == 1 and isinstance(args[0], dict):
            best = None
            for sym, subf in args[0].items():
                primary_features = {k.replace(f'_{PRIMARY_TIMEFRAME}', ''): v for k, v in subf.items() if k.endswith(f'_{PRIMARY_TIMEFRAME}')}
                if not primary_features:
                    primary_features = subf  # Fallback

                stg, why, prio = choose_strategy(primary_features)
                act, conf = choose_action(primary_features)
                rec = {"symbol": sym, "strategy": stg, "label": LABELS.get(stg, "기타"), "reason": why, "priority": prio, "action": act, "confidence": conf}
                if best is None or rec["priority"] > best["priority"]:
                    best = rec
            return best or {"symbol": symbol, "strategy": "snake_ma", "label": LABELS["snake_ma"], "reason": "입력없음", "priority": 1, "action": "hold", "confidence": 0.0}
        else:
            # 피처가 없는 경우 기본값 반환
            return {"symbol": symbol, "strategy": "snake_ma", "label": LABELS["snake_ma"], "reason": "입력없음", "priority": 1, "action": "hold", "confidence": 0.0}

    # 단일 심볼에 대한 피처 처리
    primary_features = {k.replace(f'_{PRIMARY_TIMEFRAME}', ''): v for k, v in f.items() if k.endswith(f'_{PRIMARY_TIMEFRAME}')}
    if not primary_features:
        primary_features = f  # Fallback

    stg, why, prio = choose_strategy(primary_features)
    act, conf = choose_action(primary_features)
    return {"symbol": symbol, "strategy": stg, "label": LABELS.get(stg, "기타"), "reason": why, "priority": prio, "action": act, "confidence": conf}
