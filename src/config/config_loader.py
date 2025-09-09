# -*- coding: utf-8 -*-
"""JSON 설정 파일을 로드하고, 전략별 오버라이드를 적용합니다."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
import logging

# --- 모듈 임포트 --- 
# core.trader_exit_profiles는 동적 오버라이드를 위해 필요합니다.
try:
    from ..core.trader_exit_profiles import PROFILES as EXIT_PROFILES
except ImportError:
    EXIT_PROFILES = None
    logging.warning("Exit profiles not found. Strategy overrides will not be applied.")

# --- 상수 정의 ---
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "configs"

# --- 데이터 클래스 정의 ---
@dataclass
class PretradePolicy:
    """사전 거래 안전 정책을 정의하는 데이터 클래스."""
    enable_qty_autoscale: bool = True
    reduce_rate: float = 0.9
    max_retries: int = 3
    min_notional_usdt: float = 0.0

@dataclass
class LoadedConfig:
    """로드된 모든 설정을 담는 데이터 클래스."""
    settings: Dict[str, Any] = field(default_factory=dict)
    overrides: Dict[str, Any] = field(default_factory=dict)
    risk_profiles: Dict[str, Any] = field(default_factory=dict)
    pretrade: PretradePolicy = field(default_factory=PretradePolicy)

# --- 헬퍼 함수 ---
def _read_json(path: Path) -> Dict[str, Any]:
    """JSON 파일을 안전하게 읽어 딕셔너리로 반환합니다."""
    if not path.exists():
        logging.warning(f"설정 파일을 찾을 수 없습니다: {path}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logging.error(f"JSON 파싱 오류: {path} 파일이 손상되었을 수 있습니다. {e}")
        return {}
    except Exception as e:
        logging.error(f"설정 파일 로드 중 예기치 않은 오류 발생: {path}, {e}")
        return {}

def _apply_strategy_overrides(overrides: Dict[str, Any]):
    """strategy_overrides.json 내용을 trader_exit_profiles.PROFILES에 동적으로 반영합니다."""
    if EXIT_PROFILES is None or not isinstance(overrides, dict):
        return

    strategies_to_override = overrides.get("strategies", {})
    if not isinstance(strategies_to_override, dict):
        return

    logging.info(f"{len(strategies_to_override)}개의 전략에 대한 오버라이드를 적용합니다...")
    for name, params in strategies_to_override.items():
        profile = EXIT_PROFILES.get(name)
        if not profile:
            logging.warning(f"오버라이드할 전략 프로필 '{name}'을(를) 찾을 수 없습니다.")
            continue
        
        for key, value in params.items():
            if hasattr(profile, key):
                try:
                    # 올바른 타입으로 변환 시도
                    original_type = type(getattr(profile, key))
                    setattr(profile, key, original_type(value))
                except (ValueError, TypeError):
                    logging.error(f