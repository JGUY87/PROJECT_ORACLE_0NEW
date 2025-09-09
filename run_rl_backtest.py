import argparse
import os
import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from src.core.trading_env import TradingEnv, EnvConfig

def run_rl_backtest(model_path: str, symbol: str, start_date: str):
    """
    Runs a backtest for a trained RL model.

    Args:
        model_path (str): Path to the trained PPO model .zip file.
        symbol (str): The symbol to backtest (e.g., 'BTCUSDT').
        start_date (str): The start date for the backtest data (e.g., '2023-01-01').
    """
    print(f"--- Starting RL Backtest --- ")
    print(f"Model: {model_path}")
    print(f"Symbol: {symbol}")
    print(f"Start Date: {start_date}")

    # --- 1. Load Model and Environment ---
    if not os.path.exists(model_path):
        print(f"Error: Model file not found at {model_path}")
        return

    # Derive vecnormalize path from model path
    model_dir = os.path.dirname(model_path)
    vecnormalize_path = os.path.join(model_dir, "vecnormalize.pkl")

    if not os.path.exists(vecnormalize_path):
        print(f"Error: vecnormalize.pkl not found in {model_dir}")
        return

    # Create the environment
    env_config = {
        "symbol": symbol,
        "use_online": True, # Use live data for backtest consistency
        "random_start": False # Start from the beginning of the data
    }
    env = DummyVecEnv([lambda: TradingEnv(config=env_config)])
    env = VecNormalize.load(vecnormalize_path, env)
    env.training = False # Set to evaluation mode
    env.norm_reward = False

    # Load the PPO model
    model = PPO.load(model_path, env=env)

    # --- 2. Run Backtest Loop ---
    obs = env.reset()
    done = False
    total_reward = 0.0
    trade_count = 0
    
    # Store results
    equity_history = []
    initial_equity = env.get_attr("equity")[0]
    equity_history.append(initial_equity)

    print("\n--- Backtest Running --- ")
    while not done:
        action, _states = model.predict(obs, deterministic=True)
        obs, reward, done, info = env.step(action)
        
        total_reward += reward[0]
        equity_history.append(info[0]["equity"])

        if info[0].get("realized_pnl", 0) != 0:
            trade_count += 1

    print("--- Backtest Complete ---\n")

    # --- 3. Report Results ---
    final_equity = equity_history[-1]
    total_return_pct = (final_equity / initial_equity - 1) * 100
    max_drawdown_pct = info[0]["max_drawdown"] * 100

    print("--- Performance Summary ---")
    print(f"Initial Equity: {initial_equity:.2f}")
    print(f"Final Equity:   {final_equity:.2f}")
    print(f"Total Return:   {total_return_pct:.2f}%")
    print(f"Max Drawdown:   {max_drawdown_pct:.2f}%")
    print(f"Total Trades:   {trade_count}")
    print(f"Total Reward:   {total_reward:.4f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a backtest for a trained RL model.")
    parser.add_argument("--model-path", required=True, help="Path to the trained PPO model .zip file")
    parser.add_argument("--symbol", required=True, help="Symbol to backtest (e.g., 'BTCUSDT')")
    parser.add_argument("--start-date", required=True, help="Start date for backtest data (e.g., '2023-01-01')")
    
    args = parser.parse_args()
    
    run_rl_backtest(args.model_path, args.symbol, args.start_date)
