# -*- coding: utf-8 -*-
"""
🧠 PPO/AI 모델 로더 (stable-baselines3 기반)

- 목적: PPO AI 모델과 관련 Gym 환경을 안정적으로 로드하고, 예측 및 평가 유틸리티를 제공합니다.
- 핵심 기능:
  1) 모델 경로 자동 탐색: 전략 이름에 따라 최신 모델 파일을 자동으로 찾습니다.
  2) 커스텀 Gym 환경 지원: `gymnasium.register`를 통해 커스텀 거래 환경을 동적으로 등록합니다.
  3) VecNormalize 지원: 저장된 환경 정규화 통계를 로드하여 일관된 추론을 보장합니다.
  4) 디바이스 자동 선택: PyTorch가 사용 가능한 최적의 디바이스(cuda, mps, cpu)를 자동으로 선택합니다.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# --- 환경 변수 및 기본값 --- 
MODEL_DIR = Path(os.getenv("MODEL_DIR", "outputs"))
ENV_ID = os.getenv("PPO_ENV_ID", "TradingEnv-v0")
ENV_ENTRY_POINT = os.getenv("ENV_ENTRY_POINT", "src.core.trading_env:TradingEnv")
VECNORM_PATH = os.getenv("VECNORM_PATH", "outputs/vecnormalize.pkl")
SEED = int(os.getenv("SEED", "42"))

# 전략명과 모델 파일명 패턴 매핑
STRATEGY_MODEL_MAP: Dict[str, str] = {
    "ppo": "ppo_model.zip",
    "hukwoonyam": "ppo_model_hukwoonyam*.zip",
    "wonyotti": "ppo_model_wonyotti*.zip",
    "td_mark": "ppo_model_td_mark*.zip",
    "snake_ma": "ppo_model_snake_ma*.zip",
}

# --- 선택적 의존성 처리 ---
def _select_device() -> str:
    """PyTorch가 설치된 경우, 사용 가능한 최적의 디바이스를 선택합니다."""
    try:
        import torch
        if torch.cuda.is_available():
            logging.info("[장치 선택] CUDA 사용 가능. GPU를 사용합니다.")
            return "cuda"
        if torch.backends.mps.is_available(): # Apple Silicon GPU
            logging.info("[장치 선택] MPS 사용 가능. Apple Silicon GPU를 사용합니다.")
            return "mps"
    except ImportError:
        logging.info("[장치 선택] PyTorch가 설치되지 않았습니다. CPU를 사용합니다.")
    except Exception as e:
        logging.warning(f"[장치 선택] 디바이스 확인 중 오류 발생: {e}")
    return "cpu"

# --- 모델 경로 탐색 ---
def _resolve_model_path(strategy: str) -> Optional[Path]:
    """전략명에 해당하는 최신 모델 파일의 경로를 찾습니다."""
    MODEL_DIR.mkdir(exist_ok=True)
    pattern = STRATEGY_MODEL_MAP.get(strategy, STRATEGY_MODEL_MAP["snake_ma"]) # 기본값으로 fallback
    
    paths = sorted(MODEL_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if paths:
        logging.info(f"[{strategy}] 전략에 대한 모델을 찾았습니다: {paths[0]}")
        return paths[0]
    
    # fallback 재시도
    if strategy != "snake_ma":
        logging.warning(f"[{strategy}] 전략 모델을 찾지 못해 기본 'snake_ma' 모델을 탐색합니다.")
        return _resolve_model_path("snake_ma")
        
    return None

# --- Gymnasium 환경 관리 ---
def _register_env_if_needed(env_id: str, entry_point: str):
    """필요한 경우 커스텀 Gymnasium 환경을 등록합니다."""
    try:
        import gymnasium as gym
        if env_id not in gym.envs.registry:
            gym.register(id=env_id, entry_point=entry_point)
            logging.info(f"[Gym] 커스텀 환경 등록 완료: {env_id} -> {entry_point}")
    except ImportError:
        logging.error("[Gym] `gymnasium` 라이브러리가 설치되지 않았습니다.")
    except Exception as e:
        logging.error(f"[Gym] 환경 등록 실패: {e}", exc_info=True)

def _create_vec_env(env_id: str, n_envs: int, seed: int):
    """벡터화된 Gymnasium 환경을 생성합니다."""
    try:
        from stable_baselines3.common.env_util import make_vec_env
        _register_env_if_needed(env_id, ENV_ENTRY_POINT)
        return make_vec_env(env_id, n_envs=n_envs, seed=seed)
    except ImportError:
        logging.error("[SB3] `stable-baselines3` 라이브러리가 설치되지 않았습니다.")
    except Exception as e:
        logging.error(f"[SB3] 벡터 환경 생성 실패: {e}", exc_info=True)
    return None

def _load_vec_normalize(env, path: str):
    """저장된 VecNormalize 통계가 있으면 로드합니다."""
    vecnorm_path = Path(path)
    if not env or not vecnorm_path.exists():
        return env
    try:
        from stable_baselines3.common.vec_env import VecNormalize
        vec_env = VecNormalize.load(str(vecnorm_path), env)
        vec_env.training = False # 추론 모드로 설정
        vec_env.norm_reward = False
        logging.info(f"[SB3] VecNormalize 통계 로드 완료: {path}")
        return vec_env
    except Exception as e:
        logging.warning(f"[SB3] VecNormalize 로드 실패 (무시하고 진행): {e}")
        return env

# --- 메인 모델 로더 ---
def load_ppo_model(strategy: str, device: Optional[str] = None):
    """PPO 모델을 로드하고, 관련된 환경과 설정을 초기화합니다."""
    model_path = _resolve_model_path(strategy)
    if not model_path:
        logging.error(f"'{strategy}' 전략에 대한 모델 파일을 찾을 수 없습니다.")
        return None

    try:
        from stable_baselines3 import PPO
        
        # 1. 환경 생성
        env = _create_vec_env(ENV_ID, n_envs=1, seed=SEED)
        if not env:
            raise RuntimeError("환경 생성에 실패했습니다.")

        # 2. VecNormalize 적용
        env = _load_vec_normalize(env, VECNORM_PATH)

        # 3. 모델 로드
        selected_device = device or _select_device()
        model = PPO.load(model_path, env=env, device=selected_device)
        logging.info(f"✅ PPO 모델 로드 성공: {model_path} (장치: {selected_device})")
        return model

    except ImportError:
        logging.error("AI 모델 로딩에 필요한 라이브러리(stable-baselines3, gymnasium)가 설치되지 않았습니다.")
    except Exception as e:
        logging.error(f"PPO 모델 로딩 중 오류 발생: {e}", exc_info=True)
    
    return None

# --- 추론 및 평가 유틸리티 ---
def predict_action(model, observation: Any) -> Optional[Any]:
    """로드된 모델을 사용하여 주어진 관측값에 대한 행동을 예측합니다."""
    if model is None:
        logging.error("모델이 로드되지 않아 예측할 수 없습니다.")
        return None
    try:
        action, _ = model.predict(observation, deterministic=True)
        return action
    except Exception as e:
        logging.error(f"모델 예측 중 오류 발생: {e}", exc_info=True)
        return None

# ======================= 사용 예시 =======================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info(f"📦 모델 디렉토리: {MODEL_DIR}")
    
    strategy_to_load = "hukwoonyam"
    logging.info(f"🔎 '{strategy_to_load}' 전략에 대한 모델 로딩을 시도합니다...")
    
    model = load_ppo_model(strategy_to_load)
    
    if model:
        logging.info("✅ 모델 로드 성공. 간단한 테스트를 진행합니다.")
        # TODO: 평가 로직 (quick_evaluate)은 실제 환경에 맞게 재구성 필요
    else:
        logging.error("❌ 모델 로드 실패.")