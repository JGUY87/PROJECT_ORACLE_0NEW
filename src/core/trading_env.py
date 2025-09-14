# src/core/trading_env.py
# -*- coding: utf-8 -*-
"""
커스텀 Gym 환경: TradingEnv-v0 (상태 추적 기능 확장)
- 일일 손익, 포지션 보유 기간 등 상세한 상태를 추적하여 정교한 보상 계산을 지원합니다.
"""
from __future__ import annotations
import os
import logging
import gymnasium as gym
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from .market_features import extract_market_features, get_bybit_data
from .rl.observation_builder import ObsConfig, build_obs
from .rl.action_schemes import TradeConfig, apply_action, unrealized_pnl
from .rl.reward_schemes import RewardWeights, ShapingContext, compute_reward, get_preset

logger = logging.getLogger(__name__)

@dataclass
class EnvConfig:
    symbol: str = "BTCUSDT"
    interval: str = "1"
    window: int = 60
    max_steps: int = 2_000
    initial_equity: float = 1_000.0
    max_leverage: float = 10.0
    # 리스크 및 비용 설정
    risk_dd_limit: float = 0.3
    daily_loss_limit_usdt: float = 200.0
    target_notional_frac: float = 0.1
    taker_fee: float = 0.00055
    slippage_bps: float = 2.0
    funding_rate_8h: float = 0.0
    # 보상 프로필
    reward_profile: str = "snake_ma"
    # 데이터 소스
    use_online: bool = True
    data_path: Optional[str] = None
    random_start: bool = True
    # 보상 가중치는 프로필을 통해 로드
    reward_weights: RewardWeights = field(init=False)

    def __post_init__(self):
        self.reward_weights = get_preset(self.reward_profile)

class TradingEnv(gym.Env):
    """
    Bybit 선물 거래를 위한 커스텀 Gym 환경.
    - 상태: OHLCV, 기술적 지표, 포지션 정보
    - 행동: 포지션 진입/청산/유지
    - 보상: 실현/미실현 손익, 거래 비용, 위험 조정 수익률 등
    """
    metadata = {"render.modes": ["human"], "render_fps": 1}

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.cfg = EnvConfig(**(config or {}))
        self.obs_cfg = ObsConfig(window=self.cfg.window)
        self.trade_cfg = TradeConfig(
            taker_fee=self.cfg.taker_fee, 
            slippage_bps=self.cfg.slippage_bps,
            max_leverage=self.cfg.max_leverage
        )
        
        self._load_and_prepare_data()
        self._setup_spaces()
        self.reset()

    def _setup_spaces(self):
        feat_dim = len(self.df_feat.columns)
        obs_dim = self.cfg.window * feat_dim
        if self.obs_cfg.include_state:
            obs_dim += 4
        self.observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32)
        self.action_space = gym.spaces.Discrete(9)

    def _load_and_prepare_data(self):
        # (이전과 동일, 생략)
        if self.cfg.use_online:
            self.df_raw = get_bybit_data(self.cfg.symbol, self.cfg.interval, limit=5000)
        else:
            path = self.cfg.data_path
            if path and os.path.exists(path):
                self.df_raw = pd.read_csv(path, index_col='timestamp', parse_dates=True)
            else:
                logger.warning("Local data not found, falling back to online.")
                self.df_raw = get_bybit_data(self.cfg.symbol, self.cfg.interval, limit=5000)
        
        if self.df_raw.empty:
            raise RuntimeError("Data loading failed.")
        self.df_feat = extract_market_features(self.df_raw)
        if len(self.df_feat) < self.cfg.window + 10:
            raise RuntimeError("Insufficient data for training.")

    def _reset_episode_indices(self):
        self.N = len(self.df_feat)
        min_start_idx = self.cfg.window + 1
        if self.cfg.random_start:
            max_start_idx = self.N - self.cfg.max_steps - 2
            self.start_idx = np.random.randint(min_start_idx, max(min_start_idx + 1, max_start_idx))
        else:
            self.start_idx = min_start_idx
        self.end_idx = min(self.N - 2, self.start_idx + self.cfg.max_steps)
        self.i = self.start_idx

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        self._reset_episode_indices()

        # 에피소드 전체 상태
        self.equity = float(self.cfg.initial_equity)
        self.cash = float(self.cfg.initial_equity)
        self.entry_price = 0.0
        self.size = 0.0
        self.side = 0
        self.leverage = 1.0
        self.realized_pnl = 0.0
        self.max_equity = self.equity
        self.max_drawdown = 0.0
        self._last_phi = 0.0
        
        # 상세 상태 추적 변수
        self.pos_age_bars = 0
        self.last_side = 0
        self.current_day = None
        self.daily_realized_pnl = 0.0
        self.daily_max_equity = self.equity

        return self._get_obs(), {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        # --- 1. 상태 업데이트 ---
        current_price = float(self.df_feat["close"].iloc[self.i])
        previous_side = self.side
        
        # 일일 상태 초기화
        self._update_daily_stats()

        # --- 2. 액션 적용 및 포지션 변경 ---
        realized_pnl_step, costs, flip = self._apply_action_and_update_position(action, current_price, previous_side)
        self.daily_realized_pnl += realized_pnl_step

        # --- 3. 자산 및 손익 재계산 ---
        upnl, funding_cost, daily_dd_pct = self._update_equity_and_pnl(current_price)
        total_costs = costs + funding_cost

        # --- 4. 보상 계산 ---
        reward = self._calculate_reward(realized_pnl_step, total_costs, current_price, flip, daily_dd_pct)

        # --- 5. 종료 조건 확인 ---
        terminated, truncated = self._check_termination()
        
        self.i += 1
        self.last_side = self.side
        
        info = self._get_info(upnl, reason="drawdown_limit" if terminated else "max_steps" if truncated else "")
        return self._get_obs(), float(reward), terminated, truncated, info

    def _update_daily_stats(self):
        """날짜가 바뀌면 일일 통계치를 리셋합니다."""
        current_date = self.df_feat.index[self.i].date()
        if self.current_day != current_date:
            self.current_day = current_date
            self.daily_realized_pnl = 0.0
            self.daily_max_equity = self.equity

    def _apply_action_and_update_position(self, action: int, price: float, previous_side: int) -> Tuple[float, float, int]:
        new_side, new_size, costs, exec_price = apply_action(
            action, price, self.side, self.size, self.equity, self.leverage, 
            self.trade_cfg, target_notional_frac=self.cfg.target_notional_frac
        )
        
        realized_pnl = 0.0
        flip = 1 if new_side != previous_side and previous_side != 0 and new_side != 0 else 0

        if new_size != self.size or new_side != self.side:
            if self.side != 0 and (new_side != self.side or new_size == 0):
                realized_pnl = unrealized_pnl(self.side, self.size, self.entry_price, exec_price)
                self.cash += realized_pnl
                self.realized_pnl += realized_pnl
            
            if new_side != 0 and new_size > 0:
                if self.side == new_side:
                    w1 = self.size
                    w2 = max(1e-9, new_size - self.size)
                    self.entry_price = (self.entry_price * w1 + exec_price * w2) / max(1e-9, w1 + w2)
                    self.pos_age_bars += 1
                else:
                    self.entry_price = exec_price
                    self.pos_age_bars = 1
            else:
                self.entry_price = 0.0
                self.pos_age_bars = 0

            self.side = new_side
            self.size = new_size
        else: # HOLD
            if self.side != 0:
                self.pos_age_bars += 1
        
        self.cash -= costs
        return realized_pnl, costs, flip

    def _update_equity_and_pnl(self, price: float) -> Tuple[float, float, float]:
        upnl = unrealized_pnl(self.side, self.size, self.entry_price, price)
        
        funding_cost = 0.0 # 펀딩비는 ShapingContext에서 직접 계산
        
        self.equity = self.cash + upnl
        self.max_equity = max(self.max_equity, self.equity)
        self.daily_max_equity = max(self.daily_max_equity, self.equity)
        
        drawdown = (self.max_equity - self.equity) / max(1e-9, self.max_equity)
        self.max_drawdown = max(self.max_drawdown, drawdown)
        
        daily_dd_pct = (self.daily_max_equity - self.equity) / max(1e-9, self.daily_max_equity) * 100.0
        
        return upnl, funding_cost, daily_dd_pct

    def _calculate_reward(self, realized_pnl: float, costs: float, price: float, flip: int, daily_dd_pct: float) -> float:
        feats = self.df_feat.iloc[self.i].to_dict()
        ctx = ShapingContext(
            features=feats, side=self.side, position_value=self.size * price,
            pos_age_bars=self.pos_age_bars, flip=flip,
            slippage_bps=self.cfg.slippage_bps,
            funding_rate_8h=self.cfg.funding_rate_8h,
            step_minutes=float(self.cfg.interval) if self.cfg.interval.isdigit() else 1.0,
            daily_pnl_usdt=self.daily_realized_pnl,
            daily_loss_limit_usdt=self.cfg.daily_loss_limit_usdt,
            daily_drawdown_pct=daily_dd_pct
        )
        
        delta_equity = (self.equity - self.max_equity) / max(1.0, self.cfg.initial_equity)
        
        reward, phi = compute_reward(
            self.cfg.reward_weights,
            delta_equity=delta_equity,
            realized_pnl=realized_pnl / max(1.0, self.cfg.initial_equity),
            costs=costs / max(1.0, self.cfg.initial_equity),
            risk_penalty=self.max_drawdown,
            hold_penalty=0.0001 if self.side != 0 else 0.0,
            profile=self.cfg.reward_profile,
            ctx=ctx,
            last_potential=self._last_phi
        )
        self._last_phi = phi
        return reward

    def _check_termination(self) -> Tuple[bool, bool]:
        terminated = self.max_drawdown >= self.cfg.risk_dd_limit
        truncated = self.i >= self.end_idx
        return terminated, truncated

    def _get_obs(self) -> np.ndarray:
        return build_obs(
            self.df_feat, self.i, self.obs_cfg, self.side, self.size, 
            self.equity, self.leverage, self.cfg.initial_equity, self.cfg.max_leverage
        )

    def _get_info(self, upnl: float, reason: str) -> Dict[str, Any]:
        return {
            "upnl": upnl, "realized_pnl": self.realized_pnl, "equity": self.equity,
            "max_drawdown": self.max_drawdown, "termination_reason": reason,
        }

    def render(self, mode="human"):
        print(f"Step: {self.i}, Equity: {self.equity:.2f}, Side: {self.side}, Size: {self.size:.6f}, PnL: {self.realized_pnl:.2f}")