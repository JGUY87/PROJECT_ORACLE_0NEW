# -*- coding: utf-8 -*-
"""core/strategy_recommender.py — HOLD 보강 & 표준 반환
BUY/SELL/HOLD를 균형 있게 반환. features 비존재/중립이면 HOLD.
"""
from __future__ import annotations
from typing import Any, Dict, Tuple
import numpy as np
import pandas as pd

labels = {
    "hukwoonyam":"강화학습 PPO",
    "wonyotti":"워뇨띠",
    "td_mark":"탐드마크",
    "volume_pullback":"거래량 눌림목",
    "smart_money_accumulation":"매집",
    "snake_ma":"EMA 폴백",
    "ppo":"PPO",
}
FEATURE_ORDER = ["ma_20","volatility","rsi","disparity","momentum","stoch_k","golden_cross","dead_cross","ppo_score","is_downtrend","pullback_detected","box_range","support_accumulation"]

def _is_num(x):
    try: float(x); return True
    except: return False

def as_features(obj) -> Dict[str, float]:
    if obj is None: return {}
    if isinstance(obj, dict): return {str(k): float(v) if _is_num(v) else v for k,v in obj.items()}
    if isinstance(obj, pd.Series): s=obj
    elif isinstance(obj, pd.DataFrame):
        if len(obj)==0: return {}
        s=obj.iloc[-1]
    else: s=None
    if s is not None: return {str(k): float(v) if _is_num(v) else v for k,v in s.items()}
    if isinstance(obj,(list,tuple,np.ndarray)):
        arr = np.asarray(obj).astype(float)
        arr = arr[0] if arr.ndim==2 and arr.shape[0]==1 else arr
        N=min(len(arr), len(FEATURE_ORDER))
        return {FEATURE_ORDER[i]: float(arr[i]) for i in range(N)}
    return {}

def choose_strategy(f: Dict[str, float]) -> Tuple[str,str,int]:
    ppo=f.get("ppo_score",0.0); is_down=bool(f.get("is_downtrend",False)); volsp=f.get("vol_spike",1.0); rsi=f.get("rsi",50.0)
    td=int(f.get("td_reversal",0)); pull=bool(f.get("pullback_detected",False)); box=bool(f.get("box_range",False)); acc=f.get("support_accumulation",0.0)
    if ppo>0.80: return "hukwoonyam","PPO 강화",10
    elif is_down and volsp>1.3 and rsi<30: return "wonyotti","하락+과매도+거래량급등",9
    elif volsp>1.5 and pull: return "volume_pullback","거래량 눌림목",8
    elif td==1: return "td_mark","TD 반전",7
    elif box and acc>=3: return "smart_money_accumulation","매집",6
    else: return "snake_ma","EMA 폴백",5

def choose_action(f: Dict[str, float]) -> Tuple[str,float]:
    golden=int(f.get("golden_cross",0)); dead=int(f.get("dead_cross",0))
    mom=float(f.get("momentum",0.0)); rsi=float(f.get("rsi",50.0)); stoch=float(f.get("stoch_k",50.0)); is_down=bool(f.get("is_downtrend",False))
    # 중립(HOLD)
    if (golden==0 and dead==0) and abs(mom)<=1e-3 and 45<=rsi<=55 and 30<=stoch<=70:
        return "hold", 0.0
    buy=0; buy+=2 if golden==1 else 0; buy+=1 if mom>0 else 0; buy+=1 if rsi<35 else 0; buy+=1 if stoch<20 else 0; buy+=1 if not is_down else 0
    sell=0; sell+=2 if dead==1 else 0; sell+=1 if mom<0 else 0; sell+=1 if rsi>65 else 0; sell+=1 if stoch>80 else 0; sell+=1 if is_down else 0
    if max(buy,sell)<2 or abs(buy-sell)<=1: return "hold",0.0
    return ("sell", min(1.0, sell/6.0)) if sell>buy else ("buy", min(1.0, buy/6.0))

def ai_recommend_strategy_live(*args, **kwargs) -> Dict[str, Any]:
    symbol = kwargs.pop("symbol","UNKNOWN")
    features = kwargs.pop("features", None) or kwargs.pop("multi_feats", None) or (args[0] if (len(args)==1 and not isinstance(args[0], str)) else None)
    f = as_features(features)
    if not f and len(args)==1 and isinstance(args[0], dict):
        # {symbol: features} 형태
        best=None
        for sym, subf in args[0].items():
            stg,why,prio = choose_strategy(subf); act,conf = choose_action(subf)
            rec = {"symbol":sym,"strategy":stg,"label":labels.get(stg,"기타"),"reason":why,"priority":prio,"action":act,"confidence":conf}
            if best is None or rec["priority"]>best["priority"]: best=rec
        return best or {"symbol":symbol,"strategy":"snake_ma","label":labels["snake_ma"],"reason":"입력없음","priority":1,"action":"hold","confidence":0.0}
    if not f:
        return {"symbol":symbol,"strategy":"snake_ma","label":labels["snake_ma"],"reason":"입력없음","priority":1,"action":"hold","confidence":0.0}
    stg,why,prio = choose_strategy(f); act,conf = choose_action(f)
    return {"symbol":symbol,"strategy":stg,"label":labels.get(stg,"기타"),"reason":why,"priority":prio,"action":act,"confidence":conf}