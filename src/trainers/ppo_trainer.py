# src/trainers/ppo_trainer.py
# -*- coding: utf-8 -*-
"""
PPO Trainer with MLOps Principles
- Manages the entire training pipeline for the PPO agent.
- Integrates with the custom TradingEnv.
- Incorporates MLOps best practices like configuration management, experiment tracking (TensorBoard),
  and automated best model saving using callbacks.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from typing import Dict, Any

import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback, StopTrainingOnRewardThreshold
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import VecNormalize

# NEW: Import the custom environment and other components from the new structure

# NEW: Import configuration from the dedicated config file
from .config import TRAINING_CONFIG

# ----------------------------------------------------------------------------
# Main Training Function
# ----------------------------------------------------------------------------

def train_ppo_trading(config: Dict[str, Any] = TRAINING_CONFIG):
    """
    Main function to orchestrate the PPO model training process.
    """
    logging.info("Starting PPO training pipeline...")

    # --- MLOps: Setup logging and save paths ---
    strategy_name = config["strategy_name"]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    model_dir = f"outputs/models/{strategy_name}_{timestamp}"
    log_dir = config["ppo_params"]["tensorboard_log"]
    vecnorm_path = os.path.join(model_dir, "vecnormalize.pkl")
    best_model_path = os.path.join(model_dir, "best_model")

    os.makedirs(model_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    logging.info(f"Strategy: {strategy_name}")
    logging.info(f"Model save directory: {model_dir}")
    logging.info(f"TensorBoard log directory: {log_dir}")

    # --- Environment Setup ---
    try:
        # Register the custom environment if it's not already registered
        # This allows `make_vec_env` to find the custom 'TradingEnv-v0'
        import gymnasium as gym
        # Use a robust way to check for registered environments, compatible with different gym versions
        env_registry = getattr(gym.envs.registry, "env_specs", gym.envs.registry)
        if config["env_id"] not in env_registry:
            gym.register(
                id=config["env_id"],
                entry_point="src.core.trading_env:TradingEnv",
            )

        # Create the vectorized training environment
        train_env_config = config["env_config"]
        train_env = make_vec_env(
            config["env_id"],
            n_envs=1,
            env_kwargs={"config": train_env_config}
        )
        train_env = VecNormalize(train_env, norm_obs=True, norm_reward=True)

        # Create the vectorized evaluation environment
        eval_env_config = config["env_config"]
        eval_env = make_vec_env(
            config["env_id"],
            n_envs=1,
            env_kwargs={"config": eval_env_config}
        )
        eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=True)

    except Exception as e:
        logging.error(f"Error creating Gym environment: {e}")
        logging.error("Please ensure that the custom TradingEnv is correctly registered and its dependencies are installed.")
        return

    # --- MLOps: Callbacks for evaluation and saving ---
    stop_callback = StopTrainingOnRewardThreshold(reward_threshold=config["reward_threshold"], verbose=1)
    
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=best_model_path,
        log_path=model_dir,
        eval_freq=config["eval_freq"],
        n_eval_episodes=config["eval_n_episodes"],
        deterministic=True,
        render=False,
        callback_on_new_best=stop_callback # Optional: stop training early if a good model is found
    )

    # --- Model Initialization ---
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logging.info(f"Using device: {device}")

    ppo_params = config["ppo_params"].copy()
    ppo_params["tensorboard_log"] = log_dir # Ensure the correct log dir is passed

    model = PPO(
        env=train_env,
        device=device,
        **ppo_params
    )

    # --- Training ---
    try:
        logging.info("Starting model training...")
        model.learn(
            total_timesteps=config["total_timesteps"],
            callback=eval_callback,
            log_interval=config["log_interval"],
            tb_log_name=f"{strategy_name}_{timestamp}"
        )
        logging.info("Model training finished.")

    except KeyboardInterrupt:
        logging.warning("Training interrupted by user.")
    except Exception as e:
        logging.error(f"An error occurred during training: {e}", exc_info=True)

    # --- MLOps: Save the final model and environment stats ---
    final_model_path = os.path.join(model_dir, "final_model.zip")
    model.save(final_model_path)
    train_env.save(vecnorm_path)
    logging.info(f"Final model saved to: {final_model_path}")
    logging.info(f"VecNormalize stats saved to: {vecnorm_path}")
    logging.info("To load this model, use the `load_ppo_model` function from `model_loader.py`.")
    logging.info(f"To monitor training, run: tensorboard --logdir {log_dir}")

# ----------------------------------------------------------------------------
# Standalone Execution
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    print("============================================================")
    print("          Running PPO Trainer Standalone          ")
    print("============================================================")
    # This allows the script to be run directly, e.g., `python src/trainers/ppo_trainer.py`
    # Ensure all dependencies like stable-baselines3, torch, gym, pandas are installed.
    train_ppo_trading()
    print("============================================================")
    print("                     Training Done                      ")
    print("============================================================")