# -*- coding: utf-8 -*-
"""JSON 설정 파일을 로드하고, 전략별 오버라이드를 적용합니다."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict
import logging

# --- 모듈 임포트 ---
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
                    original_type = type(getattr(profile, key))
                    setattr(profile, key, original_type(value))
                except (ValueError, TypeError) as e:
                    # 아래 라인이 끊겨서 발생한 오류 수정
                    logging.error(
                        f"전략 '{name}'의 파라미터 '{key}' 오버라이드 실패: "
                        f"값 '{value}'를 타입 '{original_type.__name__}'(으)로 변환할 수 없습니다. 오류: {e}"
                    )

# --- 메인 로더 함수 (누락된 부분 복원) ---
def load_all_configs() -> LoadedConfig:
    """
    모든 JSON 설정 파일을 로드하고, 오버라이드를 적용한 후,
    데이터 클래스에 담아 반환합니다.
    """
    # 1. 각 설정 파일 로드
    settings = _read_json(CONFIG_DIR / "settings.json")
    overrides = _read_json(CONFIG_DIR / "strategy_overrides.json")
    risk_profiles = _read_json(CONFIG_DIR / "risk_profiles.json")
    
    # 2. PretradePolicy 객체 생성
    pretrade_settings = settings.get("pretrade_policy", {})
    pretrade_policy = PretradePolicy(**pretrade_settings)

    # 3. 최종 설정 객체 생성
    loaded_config = LoadedConfig(
        settings=settings,
        overrides=overrides,
        risk_profiles=risk_profiles,
        pretrade=pretrade_policy,
    )
    
    # 4. 동적 오버라이드 적용
    _apply_strategy_overrides(overrides)
    
    logging.info("모든 설정 로드가 완료되었습니다.")
    return loaded_config

# --- 사용 예시 ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    final_configs = load_all_configs()
    
    print("\n--- Loaded Settings ---")
    print(final_configs.settings)
    
    print("\n--- Loaded Overrides ---")
    print(final_configs.overrides)
    
    print("\n--- Loaded Risk Profiles ---")
    print(final_configs.risk_profiles)
    
    print("\n--- Pretrade Policy ---")
    print(final_configs.pretrade)
