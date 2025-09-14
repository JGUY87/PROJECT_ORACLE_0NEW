# src/trainers/ppo_trainer.py
# -*- coding: utf-8 -*-
"""
PPO Trainer with MLOps Principles (Refactored)
- Manages the entire training pipeline for the PPO agent.
- Decoupled from configuration and structured for clarity and maintainability.
"""
from __future__ import annotations
import os
import logging
from datetime import datetime
from typing import Dict, Any, Tuple

import torch
import gymnasium as gym
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback, StopTrainingOnRewardThreshold
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import VecNormalize

from .config import TRAINING_CONFIG

logger = logging.getLogger(__name__)

def _setup_paths(config: Dict[str, Any]) -> Dict[str, str]:
    """훈련에 필요한 모든 경로를 설정하고 디렉토리를 생성합니다."""
    strategy_name = config.get("strategy_name", "PPO_Strategy")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    
    paths_config = config.get("paths", {})
    model_dir = os.path.join(paths_config.get("base_model_dir", "outputs/models"), f"{strategy_name}_{timestamp}")
    log_dir = paths_config.get("tensorboard_log_dir", "outputs/tensorboard_logs")
    
    os.makedirs(model_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    
    paths = {
        "model_dir": model_dir,
        "log_dir": log_dir,
        "vecnorm_path": os.path.join(model_dir, paths_config.get("vecnorm_filename", "vecnormalize.pkl")),
        "best_model_path": os.path.join(model_dir, paths_config.get("best_model_filename", "best_model")),
        "final_model_path": os.path.join(model_dir, paths_config.get("final_model_filename", "final_model.zip")),
        "tb_log_name": f"{strategy_name}_{timestamp}"
    }
    logger.info(f"Strategy: {strategy_name}")
    logger.info(f"All outputs will be saved in: {model_dir}")
    logger.info(f"TensorBoard logs available at: {log_dir}")
    return paths

def _create_environments(config: Dict[str, Any]) -> Tuple[VecNormalize, VecNormalize]:
    """훈련 및 평가용 Gym 환경을 생성하고 VecNormalize로 래핑합니다."""
    env_id = config.get("env_id", "TradingEnv-v0")
    env_config = config.get("env_config", {})
    
    try:
        # 커스텀 환경 등록
        env_registry = getattr(gym.envs.registry, "env_specs", gym.envs.registry)
        if env_id not in env_registry:
            gym.register(id=env_id, entry_point="src.core.trading_env:TradingEnv")
        
        # 훈련 환경 생성
        train_env = make_vec_env(env_id, n_envs=1, env_kwargs={"config": env_config})
        train_env = VecNormalize(train_env, norm_obs=True, norm_reward=True)
        
        # 평가 환경 생성
        eval_env = make_vec_env(env_id, n_envs=1, env_kwargs={"config": env_config})
        eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=True)
        
        logger.info("Training and evaluation environments created successfully.")
        return train_env, eval_env
    except Exception as e:
        logger.error(f"Gym 환경 생성 오류: {e}", exc_info=True)
        raise RuntimeError("Gym 환경을 생성하지 못했습니다. TradingEnv가 올바르게 설치 및 등록되었는지 확인하세요.")

def _setup_callbacks(config: Dict[str, Any], eval_env: VecNormalize, paths: Dict[str, str]) -> EvalCallback:
    """모델 평가 및 저장을 위한 콜백을 설정합니다."""
    stop_callback = StopTrainingOnRewardThreshold(
        reward_threshold=config.get("reward_threshold", 1000.0), verbose=1
    )
    
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=paths["best_model_path"],
        log_path=paths["model_dir"],
        eval_freq=config.get("eval_freq", 10000),
        n_eval_episodes=config.get("eval_n_episodes", 10),
        deterministic=True,
        render=False,
        callback_on_new_best=stop_callback
    )
    logger.info("Evaluation callback configured.")
    return eval_callback

def train_ppo_trading(config: Dict[str, Any] = None):
    """PPO 모델 훈련 파이프라인을 조율하는 메인 함수."""
    if config is None:
        config = TRAINING_CONFIG
        
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("PPO training pipeline started.")

    try:
        # 1. 경로 설정
        paths = _setup_paths(config)
        
        # 2. 환경 생성
        train_env, eval_env = _create_environments(config)
        
        # 3. 콜백 설정
        eval_callback = _setup_callbacks(config, eval_env, paths)
        
        # 4. 모델 초기화
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {device}")
        
        ppo_params = config.get("ppo_params", {}).copy()
        ppo_params["tensorboard_log"] = paths["log_dir"]
        
        model = PPO(env=train_env, device=device, **ppo_params)
        
        # 5. 훈련 시작
        logger.info("Starting model training...")
        model.learn(
            total_timesteps=config.get("total_timesteps", 1_000_000),
            callback=eval_callback,
            log_interval=config.get("log_interval", 1),
            tb_log_name=paths["tb_log_name"]
        )
        logger.info("Model training finished.")

    except (RuntimeError, KeyboardInterrupt) as e:
        logger.warning(f"Training stopped or failed: {e}")
        return
    except Exception as e:
        logger.error(f"An unexpected error occurred during the training pipeline: {e}", exc_info=True)
        return
    
    # 6. 최종 모델 및 환경 통계 저장
    model.save(paths["final_model_path"])
    train_env.save(paths["vecnorm_path"])
    logger.info(f"Final model saved to: {paths['final_model_path']}")
    logger.info(f"VecNormalize stats saved to: {paths['vecnorm_path']}")
    logger.info(f"To monitor training, run: tensorboard --logdir {paths['log_dir']}")

if __name__ == "__main__":
    print("="*60)
    print("          Running PPO Trainer Standalone          ")
    print("="*60)
    train_ppo_trading()
    print("="*60)
    print("                     Training Done                      ")
    print("="*60)
