# -*- coding: utf-8 -*-
from __future__ import annotations
"""
🧠 PPO/AI 모델 로더 (stable-baselines3 기반) - 최종 안정화 버전
- Windows 경로 문제 해결 (glob.glob 사용)
- 선택적 의존성 처리 (TYPE_CHECKING)
- 중복 코드 제거 및 로직 명확화
- 백업 모델 로딩 로직 강화
"""
import os
import glob
from pathlib import Path
from typing import Optional, Tuple, TYPE_CHECKING

from loguru import logger

# TYPE_CHECKING이 True일 때는 타입 검사 시에만 임포트 (런타임 오류 방지)
if TYPE_CHECKING:
    import numpy as np
    import pandas as pd
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv

# --- 경로 상수 정의 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_MODEL_DIR = PROJECT_ROOT / "outputs/models"
BACKUP_MODEL_PATH = PROJECT_ROOT / "models/ppo/backup/ppo_model.zip"


def get_latest_model_path(model_dir: str = str(DEFAULT_MODEL_DIR)) -> Optional[str]:
    """
    지정된 디렉토리 및 모든 하위 디렉토리에서 가장 최근에 수정된 .zip 모델 파일을 찾습니다.
    Windows의 절대 경로 패턴 문제를 해결하기 위해 glob.glob을 사용합니다.
    """
    try:
        # 재귀적으로 모든 .zip 파일을 찾기 위한 패턴
        search_pattern = os.path.join(model_dir, '**', '*.zip')
        list_of_files = glob.glob(search_pattern, recursive=True)

        if not list_of_files:
            logger.warning(f"'{model_dir}' 및 하위 디렉토리에서 모델 파일(.zip)을 찾을 수 없습니다.")
            return None

        # 수정 시간을 기준으로 가장 최신 파일 찾기
        latest_file = max(list_of_files, key=os.path.getctime)
        logger.info(f"가장 최신 모델을 찾았습니다: {latest_file}")
        return latest_file
    except Exception as e:
        logger.error(f"최신 모델 경로 검색 중 오류 발생: {e}", exc_info=True)
        return None


def load_ppo_model(model_path: Optional[str]) -> Optional["PPO"]:
    """
    지정된 경로에서 PPO 모델을 로드합니다. 경로가 없거나 실패 시 백업 모델을 시도합니다.
    """
    try:
        # stable-baselines3는 무거우므로, 실제 사용될 때 임포트
        from stable_baselines3 import PPO
    except ImportError:
        logger.error("[SB3] `stable-baselines3`가 설치되지 않았습니다. AI 기능을 사용할 수 없습니다. `pip install stable-baselines3`로 설치해주세요.")
        return None

    # 1. 제공된 모델 경로 시도
    if model_path and os.path.exists(model_path):
        try:
            logger.info(f"PPO 모델을 로드합니다: {model_path}")
            model = PPO.load(model_path)
            logger.info("PPO 모델 로딩 완료.")
            return model
        except Exception as e:
            logger.error(f"모델 '{model_path}' 로딩 중 오류 발생: {e}", exc_info=True)
            # 기본 모델 로드 실패 시 백업으로 넘어감

    # 2. 백업 모델 시도
    logger.warning("기본 모델을 로드할 수 없거나 경로가 제공되지 않았습니다. 백업 모델 로드를 시도합니다.")
    if BACKUP_MODEL_PATH.exists():
        try:
            logger.info(f"백업 모델을 로드합니다: {BACKUP_MODEL_PATH}")
            model = PPO.load(str(BACKUP_MODEL_PATH))
            logger.success("백업 PPO 모델 로딩 완료.")
            return model
        except Exception as e:
            logger.error(f"백업 모델 '{BACKUP_MODEL_PATH}' 로딩 중 오류 발생: {e}", exc_info=True)

    # 3. 모든 시도 실패
    logger.error("기본 및 백업 모델을 모두 찾거나 로드할 수 없습니다.")
    return None


def create_vector_env(df: "pd.DataFrame",
                      initial_balance: float = 1000.0,
                      look_back_period: int = 30,
                      max_steps: int = 200,
                      log_dir: str = "outputs/tensorboard_logs") -> Optional["DummyVecEnv"]:
    """
    주어진 데이터프레임으로 안정적인 학습/추론을 위한 벡터화된 Gym 환경을 생성합니다.
    """
    try:
        from stable_baselines3.common.vec_env import DummyVecEnv
        from src.core.trading_env import TradingEnv
    except ImportError as e:
        logger.error(f"환경 생성에 필요한 라이브러리 임포트 실패: {e}. `pip install stable-baselines3 gymnasium pandas`를 확인하세요.")
        return None

    if df is None or df.empty:
        logger.error("환경 생성을 위한 데이터프레임이 비어있습니다.")
        return None

    try:
        env_lambda = lambda: TradingEnv(
            df=df,
            initial_balance=initial_balance,
            look_back_period=look_back_period,
            max_steps=max_steps,
            log_dir=log_dir
        )
        env = DummyVecEnv([env_lambda])
        logger.info("Gym 벡터 환경을 성공적으로 생성했습니다.")
        return env
    except Exception as e:
        logger.error(f"Gym 벡터 환경 생성 중 예상치 못한 오류 발생: {e}", exc_info=True)
        return None


def predict_action(model: "PPO", obs: "np.ndarray") -> Tuple[Optional["np.ndarray"], Optional["np.ndarray"]]:
    """
    주어진 관측(observation)에 대해 모델의 행동을 예측합니다.
    """
    if model is None:
        logger.warning("모델이 없어 예측을 수행할 수 없습니다.")
        return None, None
    try:
        action, _states = model.predict(obs, deterministic=True)
        return action, _states
    except Exception as e:
        logger.error(f"모델 예측 중 오류 발생: {e}", exc_info=True)
        # 오류 발생 시 기본 행동 (중립) 반환
        import numpy as np
        return np.array([1]), None
