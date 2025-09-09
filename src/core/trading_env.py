# src/core/trading_env.py
# -*- coding: utf-8 -*-
"""
커스텀 Gym 환경: TradingEnv-v0
- 1분봉 기준 스텝 전개(기본), 멀티타임프레임 피처를 관측으로 제공
- 액션: discrete 9 (action_schemes.apply_action)
- 비용: 수수료/슬리피지/펀딩
- 리워드: reward_schemes.compute_reward (프로파일별 shaping)
- 데이터: src.core.data_manager.load_price_data 또는 src.core.market_features.get_bybit_data
"""

from __future__ import annotations
import os
import gymnasium as gym
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from dataclasses import dataclass

# NEW: 상대 경로로 임포트 수정
from .market_features import extract_market_features, get_bybit_data
from .rl.observation_builder import ObsConfig, build_obs
from .rl.action_schemes import TradeConfig, apply_action, unrealized_pnl
from .rl.reward_schemes import RewardWeights, ShapingContext, compute_reward

@dataclass
class EnvConfig:
    symbol: str = "BTCUSDT"
    interval: str = "1"
    window: int = 60
    max_steps: int = 2_000
    initial_equity: float = 1_000.0
    max_leverage: float = 10.0
    risk_dd_limit: float = 0.3
    target_notional_frac: float = 0.1
    # 비용/체결
    taker_fee: float = 0.00055
    slippage_bps: float = 2.0
    funding_rate_hourly: float = 0.0
    # 보상 가중
    reward_weights: RewardWeights = RewardWeights()
    profile: str = "snake_ma"  # 'wonyotti','td_mark','smart_money_accumulation','hukwoonyam','snake_ma'
    # 데이터 소스
    use_online: bool = False  # True면 get_bybit_data 사용, False면 로컬 df 사용
    data_path: Optional[str] = None
    # 에피소드 랜덤 시작
    random_start: bool = True

class TradingEnv(gym.Env):
    metadata = {"render.modes": ["human"]}
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.cfg = EnvConfig(**(config or {}))
        self.obs_cfg = ObsConfig(window=self.cfg.window)
        self.trade_cfg = TradeConfig(taker_fee=self.cfg.taker_fee, slippage_bps=self.cfg.slippage_bps,
                                     max_leverage=self.cfg.max_leverage, funding_rate_hourly=self.cfg.funding_rate_hourly)
        self.rw = self.cfg.reward_weights

        # 관측/액션 공간
        feat_dim = len(self.obs_cfg.feature_cols)
        self.observation_space = gym.spaces.Box(low=-np.inf, high=np.inf, shape=(self.cfg.window*feat_dim + (4 if self.obs_cfg.include_state else 0), ), dtype=np.float32)
        self.action_space = gym.spaces.Discrete(9)

        # 데이터 로드
        self.df_raw = self._load_data()
        self.df_feat = extract_market_features(self.df_raw)
        if self.df_feat.empty or len(self.df_feat) < (self.cfg.window + 10):
            raise RuntimeError("훈련 데이터가 부족합니다.")
        self._reset_index_range()

        # 상태
        self.reset()

    # 데이터 로드
    def _load_data(self) -> pd.DataFrame:
        if self.cfg.use_online:
            df = get_bybit_data(self.cfg.symbol, self.cfg.interval, limit=5000)
            if df.empty:
                raise RuntimeError("온라인 데이터 로딩 실패")
            return df
        else:
            # 로컬 csv 경로 제공 시
            if self.cfg.data_path and os.path.exists(self.cfg.data_path):
                return pd.read_csv(self.cfg.data_path)
            # 폴백: 온라인
            return get_bybit_data(self.cfg.symbol, self.cfg.interval, limit=5000)

    def _reset_index_range(self):
        self.N = len(self.df_feat)
        self.start_idx = self.cfg.window + 1
        if self.cfg.random_start:
            self.start_idx = np.random.randint(self.cfg.window + 1, max(self.cfg.window + 2, self.N - self.cfg.max_steps - 1))
        self.end_idx = min(self.N - 2, self.start_idx + self.cfg.max_steps)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        # Gymnasium API에 따라 SEED를 설정합니다.
        super().reset(seed=seed)

        self._reset_index_range()
        self.i = self.start_idx
        self.equity = float(self.cfg.initial_equity)
        self.cash = float(self.cfg.initial_equity)
        self.entry_price = 0.0
        self.size = 0.0
        self.side = 0          # -1/0/1
        self.leverage = 1.0
        self.realized_pnl = 0.0
        self.max_equity = self.equity
        self.max_drawdown = 0.0
        self._last_phi = 0.0

        obs = self._obs()
        # Gymnasium API는 관측과 함께 정보 딕셔너리를 반환해야 합니다.
        info = {}
        return obs, info

    def _obs(self):
        return build_obs(self.df_feat, self.i, self.obs_cfg, self.side, self.size, self.equity, self.leverage)

    def step(self, action: int):
        # 현재가
        price = float(self.df_feat["close"].iloc[self.i])

        # 액션 적용
        new_side, new_size, costs, exec_price = apply_action(
            action, price, self.side, self.size, self.equity, self.leverage, self.trade_cfg, target_notional_frac=self.cfg.target_notional_frac
        )

        # 체결/포지션 갱신
        realized = 0.0
        if self.side != 0 and new_side == 0:
            # 전체 청산이면 실현
            realized = unrealized_pnl(self.side, self.size, self.entry_price, exec_price)
            self.cash += realized - costs
            self.realized_pnl += realized - costs
            self.size = 0.0
            self.side = 0
            self.entry_price = 0.0
        else:
            # 신규/증가/감소/반전
            if new_side != 0:
                if self.side == 0:
                    # 신규 진입
                    self.entry_price = exec_price
                    self.size = new_size
                    self.side = new_side
                    self.cash -= costs
                else:
                    # 증감/반전 시 평균가격 근사 업데이트
                    self.cash -= costs
                    if new_side == self.side:
                        # 단순 증감
                        w1 = self.size
                        w2 = max(1e-9, new_size - self.size)
                        self.entry_price = (self.entry_price * w1 + exec_price * w2) / max(1e-9, (w1 + w2))
                        self.size = new_size
                    else:
                        # 반전: 이전 미실현을 실현하고 새 진입으로 간주
                        realized = unrealized_pnl(self.side, self.size, self.entry_price, exec_price)
                        self.cash += realized
                        self.realized_pnl += realized
                        self.entry_price = exec_price
                        self.side = new_side
                        self.size = new_size

        # 미실현 PnL 및 에쿼티
        upnl = unrealized_pnl(self.side, self.size, self.entry_price, price)
        # 펀딩 소액(분 단위 단순화)
        funding_cost = 0.0
        if self.trade_cfg.funding_rate_hourly != 0 and self.side != 0:
            funding_cost = self.size * price * (self.trade_cfg.funding_rate_hourly / 60.0)
            self.cash -= funding_cost

        self.equity = self.cash + upnl
        self.max_equity = max(self.max_equity, self.equity)
        self.max_drawdown = max(self.max_drawdown, (self.max_equity - self.equity) / max(1e-9, self.max_equity))

        # 보상 계산
        feats = self.df_feat.iloc[self.i]
        ctx = ShapingContext(
            features=feats.to_dict(),
            side=self.side,
            position_value=self.size*price,
            ema20=float(feats.get("ema20", np.nan)),
            ema50=float(feats.get("ema50", np.nan)),
            rsi14=float(feats.get("rsi14", np.nan)),
            td_up=float(feats.get("td_up", 0.0)) if "td_up" in feats else 0.0,
            td_down=float(feats.get("td_down", 0.0)) if "td_down" in feats else 0.0,
            bb_width=float(feats.get("bb_width", np.nan)) if "bb_width" in feats else np.nan,
            vol_spike=float(feats.get("vol_spike", np.nan)) if "vol_spike" in feats else np.nan,
            mom_5=float(feats.get("mom_5", np.nan)) if "mom_5" in feats else np.nan,
            mom_60=float(feats.get("mom_60", np.nan)) if "mom_60" in feats else np.nan,
            ha_up=int(feats.get("ha_up", 0)) if "ha_up" in feats else 0,
        )

        delta_equity = (self.equity - self.max_equity) / max(1.0, self.cfg.initial_equity)  # 상대 변화(보수적)
        risk_penalty = self.max_drawdown
        hold_penalty = 0.0
        if self.side != 0:
            hold_penalty = 0.0001  # 지나친 홀딩 페널티(소량)

        reward, phi = compute_reward(
            self.rw,
            delta_equity=delta_equity,
            realized_pnl=realized / max(1.0, self.cfg.initial_equity),
            costs=(costs + funding_cost) / max(1.0, self.cfg.initial_equity),
            risk_penalty=risk_penalty,
            hold_penalty=hold_penalty,
            profile=self.cfg.profile,
            ctx=ctx,
            last_potential=self._last_phi
        )
        self._last_phi = phi

        # 다음 스텝
        self.i += 1
        
        # Gymnasium API에 따라 종료 조건을 terminated와 truncated로 분리합니다.
        terminated = self.max_drawdown >= self.cfg.risk_dd_limit
        truncated = self.i >= self.end_idx
        
        reason = ""
        if terminated:
            reason = "drawdown_limit"
        elif truncated:
            reason = "max_steps"

        obs = self._obs()
        info = {
            "upnl": upnl,
            "realized_pnl": self.realized_pnl,
            "equity": self.equity,
            "max_drawdown": self.max_drawdown,
            "terminated_reason": reason,
            "episode_reward": reward
        }
        # Gymnasium API는 5개의 값을 반환해야 합니다: (관측, 보상, 완전종료, 중간종료, 정보)
        return obs, float(reward), terminated, truncated, info

    def render(self, mode="human"):
        print(f"i={self.i}, equity={self.equity:.2f}, side={self.side}, size={self.size:.6f}, entry={self.entry_price:.2f}")
