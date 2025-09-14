# src/trainers/config.py
# -*- coding: utf-8 -*-
"""
PPO Trainer 중앙 설정 파일
- 훈련 파이프라인의 모든 하이퍼파라미터와 경로 설정을 관리합니다.
"""

import torch

# --- MLOps: 기본 경로 설정 ---
BASE_OUTPUT_DIR = "outputs"
BASE_MODEL_DIR = f"{BASE_OUTPUT_DIR}/models"
TENSORBOARD_LOG_DIR = f"{BASE_OUTPUT_DIR}/tensorboard_logs"
VECNORM_FILENAME = "vecnormalize.pkl"
BEST_MODEL_FILENAME = "best_model"
FINAL_MODEL_FILENAME = "final_model.zip"

# --- 훈련 설정 --- 
TRAINING_CONFIG = {
    # 전략 및 환경 ID
    "strategy_name": "PPO_Trading_Strategy",
    "env_id": "TradingEnv-v0",

    # 훈련 루프 설정
    "total_timesteps": 1_000_000,
    "log_interval": 1,
    
    # 평가 및 조기 종료 설정
    "eval_freq": 10_000,
    "eval_n_episodes": 10,
    "reward_threshold": 1000.0, # 조기 종료를 위한 목표 보상

    # 환경(TradingEnv) 설정
    "env_config": {
        "symbol": "BTC/USDT",
        "interval": "5m",
        "window": 60,
        "initial_equity": 1000.0,
        "max_leverage": 10.0,
        "risk_dd_limit": 0.5,
        "daily_loss_limit_usdt": 200.0,
        "reward_profile": "snake_ma",
        "use_online": True, # 실시간 데이터로 훈련 시 True
        "data_path": None, # 로컬 데이터 사용 시 경로 지정
    },

    # PPO 하이퍼파라미터 (stable-baselines3)
    "ppo_params": {
        "policy": "MlpPolicy",
        "learning_rate": 3e-4,
        "n_steps": 2048,
        "batch_size": 64,
        "n_epochs": 10,
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_range": 0.2,
        "ent_coef": 0.0,
        "vf_coef": 0.5,
        "max_grad_norm": 0.5,
        "verbose": 1,
        "seed": 42,
        "policy_kwargs": {
            "activation_fn": torch.nn.ReLU,
            "net_arch": [dict(pi=[128, 128], vf=[128, 128])],
        },
        # tensorboard_log는 trainer에서 동적으로 설정됩니다.
        "tensorboard_log": TENSORBOARD_LOG_DIR,
    },

    # 경로 설정
    "paths": {
        "base_model_dir": BASE_MODEL_DIR,
        "tensorboard_log_dir": TENSORBOARD_LOG_DIR,
        "vecnorm_filename": VECNORM_FILENAME,
        "best_model_filename": BEST_MODEL_FILENAME,
        "final_model_filename": FINAL_MODEL_FILENAME,
    }
}