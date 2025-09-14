# -*- coding: utf-8 -*-
"""
데이터 룩백 기간 설정을 위한 설정 파일
"""

LOOKBACK_CONFIG = {
    "1m":  {"core_days": 45,  "wf_days": 14, "oos_days": 14, "min_bars": 20000},
    "3m":  {"core_days": 60,  "wf_days": 21, "oos_days": 14, "min_bars": 20000},
    "5m":  {"core_days": 90,  "wf_days": 21, "oos_days": 21, "min_bars": 20000},
    "15m": {"core_days": 210, "wf_days": 45, "oos_days": 45, "min_bars": 17000},
    "1h":  {"core_days": 365, "wf_days": 90, "oos_days": 90, "min_bars": 7000},
    "4h":  {"core_days": 730, "wf_days": 120,"oos_days": 120,"min_bars": 5000},
    "1d":  {"core_days": 1825,"wf_days": 240,"oos_days": 240,"min_bars": 800},
}

def required_min_bars(longest_period:int, tf:str) -> int:
    """
    가장 긴 지표 기간과 타임프레임을 기반으로 최소 필요한 캔들 수를 계산합니다.
    """
    # Map ccxt timeframes to LOOKBACK_CONFIG keys
    timeframe_mapping = {
        "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m",
        "1h": "1h", "2h": "4h", "4h": "4h", "6h": "4h", "12h": "4h",
        "1d": "1d", "1w": "1d", "1M": "1d"
    }
    mapped_tf = timeframe_mapping.get(tf, "1h") # Default to 1h if not found

    base = LOOKBACK_CONFIG[mapped_tf]["min_bars"]
    return max(3 * longest_period, base)
