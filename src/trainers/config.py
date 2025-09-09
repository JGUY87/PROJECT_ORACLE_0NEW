# src/trainers/config.py
# -*- coding: utf-8 -*-
"""
Configuration for the PPO Trainer
- Centralized management of hyperparameters and environment settings.
- This allows for easy adjustments and versioning of experiment configurations.
"""

# In a production MLOps setup, this could be loaded from a YAML/JSON file
# or managed by a tool like Hydra or Sacred.

TRAINING_CONFIG = {
    "env_id": "TradingEnv-v0",
    "strategy_name": "default_ppo",
    "total_timesteps": 1_000_000, # Total steps for training
    "log_interval": 1, # Log every N episodes
    
    # PPO Hyperparameters (tuned for general purpose, may need adjustment)
    "ppo_params": {
        "policy": "MlpPolicy",
        "learning_rate": 3e-4,
        "n_steps": 2048, # Number of steps to run for each environment per update
        "batch_size": 64,
        "n_epochs": 10,
        "gamma": 0.99, # Discount factor
        "gae_lambda": 0.95, # Factor for trade-off of bias vs variance for GAE
        "clip_range": 0.2, # Clipping parameter, it can be a function
        "ent_coef": 0.0, # Entropy coefficient for exploration
        "vf_coef": 0.5, # Value function coefficient for the loss calculation
        "max_grad_norm": 0.5, # The maximum value for the gradient clipping
        "tensorboard_log": "outputs/tensorboard_logs/",
        "verbose": 1,
    },
    
    # Environment Configuration
    "env_config": {
        "symbol": "BTCUSDT",
        "interval": "1", # 1-minute interval
        "window": 60, # Observation window size
        "max_steps": 2000, # Max steps per episode
        "initial_equity": 1000.0,
        "max_leverage": 5.0,
        "profile": "snake_ma", # Reward profile from reward_schemes.py
        "use_online": True, # Use live data from Bybit for training (can be slow and costly)
    },

    # MLOps: Evaluation and Model Saving Configuration
    "eval_freq": 8192, # Evaluate the model every N steps
    "eval_n_episodes": 5, # Number of episodes to run for evaluation
    "reward_threshold": 100.0, # Stop training if this average reward is reached
}
