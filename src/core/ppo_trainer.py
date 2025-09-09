# src/core/ppo_trainer.py
# -*- coding: utf-8 -*-
"""
Shim for PPO Trainer
- Dynamically imports and calls the actual trainer from src.trainers.ppo_trainer
"""

def train_ppo_trading(*args, **kwargs):
    """
    Dynamically imports and calls the actual PPO training function.
    This acts as a bridge, decoupling the core engine from the training implementation.
    """
    try:
        # NEW: Adjusted import path for the new structure
        from importlib import import_module
        # Assuming the actual trainer is in src/trainers/ppo_trainer.py
        mod = import_module('src.trainers.ppo_trainer')
        
        if hasattr(mod, 'train_ppo_trading'):
            print("[PPO-SHIM] Forwarding call to src.trainers.ppo_trainer.train_ppo_trading")
            return mod.train_ppo_trading(*args, **kwargs)
        else:
            print("[PPO-SHIM] Error: 'train_ppo_trading' function not found in src.trainers.ppo_trainer")

    except ImportError as e:
        print(f"[PPO-SHIM] Could not import trainer module. Skipping training. Error: {e}")
    except Exception as e:
        print(f"[PPO-SHIM] An unexpected error occurred: {e}")
    
    return None