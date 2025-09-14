# src/core/rl/reward_schemes.py
# -*- coding: utf-8 -*-
"""
리워드 스킴 v2.4 (설정 유연성 및 구조 개선)
- 기본 보상: (수익 - 비용 - 리스크) + 잠재기반 shaping(Φ_t - γΦ_{t-1})
- 구조 개선: 메인 보상 계산 함수를 분해하여 가독성 및 유지보수성 향상
- 유연성 향상: 페널티 계산에 사용되는 임계값들을 RewardWeights 설정으로 분리
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Callable, Any
import math
import logging

logger = logging.getLogger(__name__)

# --- 안전 유틸리티 ---
def _f(x: Any, default: float = 0.0) -> float:
    """값이 유한한 float인지 확인하고, 아니면 기본값을 반환합니다."""
    try:
        v = float(x)
        return v if math.isfinite(v) else float(default)
    except (ValueError, TypeError):
        return float(default)

def _clip(x: float, lo: float, hi: float) -> float:
    """값을 주어진 범위(lo, hi) 내로 제한합니다."""
    return max(lo, min(x, hi))

def _softplus(x: float) -> float:
    """수학적으로 안정적인 softplus 함수. overflow를 방지합니다."""
    if x > 50:
        return x
    if x < -50:
        return 0.0
    return math.log1p(math.exp(x))

# --- 설정 데이터 클래스 ---
@dataclass
class RewardWeights:
    pnl: float = 1.0
    realized: float = 0.5
    cost: float = 1.0
    risk: float = 0.5
    hold: float = 0.0
    churn: float = 0.2
    slip: float = 0.6
    funding: float = 0.4
    loss_cut: float = 2.0
    drawdown: float = 0.3
    profile: float = 0.3
    scale: float = 1.0
    # 페널티 상세 설정
    churn_max_age_strong: int = 2
    churn_max_age_weak: int = 1
    loss_barrier_start_pct: float = 0.7

@dataclass
class ShapingContext:
    side: int = 0
    position_value: float = 0.0
    pos_age_bars: int = 0
    flip: int = 0
    features: Dict[str, float] = field(default_factory=dict)
    # 확장 피처
    slippage_bps: float = math.nan
    funding_rate_8h: float = math.nan
    step_minutes: float = 1.0
    daily_pnl_usdt: float = 0.0
    daily_loss_limit_usdt: float = 0.0
    daily_drawdown_pct: float = math.nan

# --- 잠재력 기반 Shaping 함수들 ---
def potential_snake_ma(ctx: ShapingContext) -> float:
    e20 = _f(ctx.features.get('EMA_20'))
    e50 = _f(ctx.features.get('EMA_50'))
    if e20 == 0 and e50 == 0:
        return 0.0
    is_aligned = (e20 > e50 and ctx.side >= 0) or (e20 < e50 and ctx.side <= 0)
    return 0.5 if is_aligned else -0.2

# ... (다른 potential 함수들은 변경 없음)
POTENTIALS: Dict[str, Callable[[ShapingContext], float]] = {"snake_ma": potential_snake_ma}

# --- 페널티 계산 로직 ---
def _calculate_contextual_penalties(ctx: ShapingContext, weights: RewardWeights) -> Dict[str, float]:
    """컨텍스트 정보를 바탕으로 각종 페널티를 계산합니다."""
    penalties = {
        "churn": 0.0, "slippage": 0.0, "funding": 0.0,
        "loss_barrier": 0.0, "drawdown": 0.0
    }
    # 과매매 페널티
    flip = int(_f(ctx.flip, 0))
    age = max(0, int(_f(ctx.pos_age_bars, 0)))
    if flip == 1 and age <= weights.churn_max_age_strong:
        penalties["churn"] = 1.0
    elif age <= weights.churn_max_age_weak:
        penalties["churn"] = 0.5

    # 슬리피지 페널티 (bps를 비율로 변환)
    penalties["slippage"] = max(0.0, _f(ctx.slippage_bps)) / 10000.0

    # 펀딩비 페널티 (지불해야 하는 경우만 계산)
    rate8h = _f(ctx.funding_rate_8h)
    if (ctx.side > 0 and rate8h > 0) or (ctx.side < 0 and rate8h < 0):
        step_h = max(0.0, _f(ctx.step_minutes, 1.0) / 60.0)
        penalties["funding"] = abs(rate8h) * (step_h / 8.0)

    # 일일 손실 제한 페널티 (Soft Barrier)
    limit = _f(ctx.daily_loss_limit_usdt)
    if limit > 0:
        pnl = _f(ctx.daily_pnl_usdt)
        loss_ratio = max(0.0, -pnl / limit)
        penalties["loss_barrier"] = _softplus(loss_ratio - weights.loss_barrier_start_pct)

    # 일일 최대 낙폭 페널티
    dd_pct = _f(ctx.daily_drawdown_pct)
    if dd_pct > 0:
        penalties["drawdown"] = dd_pct / 100.0
        
    return penalties

# --- 메인 보상 계산 함수 ---
def compute_reward(
    weights: RewardWeights,
    delta_equity: float,
    realized_pnl: float,
    costs: float,
    risk_penalty: float,
    hold_penalty: float,
    profile: str,
    ctx: Optional[ShapingContext] = None,
    gamma: float = 0.99,
    last_potential: float = 0.0,
    clip_range: float = 1.0,
    tanh_scale: float = 1.0,
) -> Tuple[float, float]:
    """
    모든 요소를 종합하여 최종 보상을 계산합니다.
    반환: (총 보상, 현재 잠재력 값 Φ)
    """
    # 1. 기본 보상 요소
    base_reward = (
        weights.pnl * _f(delta_equity) +
        weights.realized * _f(realized_pnl) -
        weights.cost * abs(_f(costs)) -
        weights.risk * abs(_f(risk_penalty)) -
        weights.hold * abs(_f(hold_penalty))
    )
    
    # 2. 컨텍스트 기반 페널티
    phi = 0.0
    context_penalty = 0.0
    if ctx:
        penalties = _calculate_contextual_penalties(ctx, weights)
        context_penalty = (
            weights.churn * penalties["churn"] +
            weights.slip * penalties["slippage"] +
            weights.funding * penalties["funding"] +
            weights.loss_cut * penalties["loss_barrier"] +
            weights.drawdown * penalties["drawdown"]
        )
        
        # 3. 잠재력 기반 Shaping
        if weights.profile > 0:
            potential_func = POTENTIALS.get(profile, lambda *_: 0.0)
            phi = float(potential_func(ctx))

    # 4. 최종 보상 조합
    shaped_reward = base_reward - context_penalty
    if ctx and weights.profile > 0:
        effective_gamma = _clip(float(gamma), 0.0, 0.999)
        shaping_value = phi - effective_gamma * _f(last_potential)
        shaped_reward += weights.profile * shaping_value

    # 5. 후처리 (스케일링 및 클리핑)
    final_reward = shaped_reward * float(weights.scale or 1.0)
    if tanh_scale > 0:
        final_reward = math.tanh(final_reward * float(tanh_scale))
    if clip_range > 0:
        final_reward = _clip(final_reward, -abs(clip_range), abs(clip_range))

    return float(final_reward), float(phi)

# --- 프리셋 ---
PRESETS: Dict[str, RewardWeights] = {
    "default": RewardWeights(),
    "snake_ma": RewardWeights(pnl=1.0, realized=0.4, cost=0.9, risk=0.4, hold=0.2, churn=0.2, slip=0.6, funding=0.3, loss_cut=2.0, drawdown=0.25, profile=0.4),
    # ... 다른 프리셋들
}

def get_preset(profile: str) -> RewardWeights:
    return PRESETS.get(profile, RewardWeights())

# --- 자체 테스트 ---
if __name__ == "__main__":
    w = get_preset("snake_ma")
    ctx = ShapingContext(
        side=1, pos_age_bars=1, flip=1,
        features={'EMA_20': 101, 'EMA_50': 100},
        slippage_bps=12.0, funding_rate_8h=0.01,
        daily_pnl_usdt=-150.0, daily_loss_limit_usdt=200.0, daily_drawdown_pct=2.5
    )
    r, p = compute_reward(
        w, delta_equity=0.005, realized_pnl=0, costs=0.0008, risk_penalty=0.0012, 
        hold_penalty=0.0, profile="snake_ma", ctx=ctx
    )
    print(f"Reward: {r:.6f}, Phi: {p:.4f}")