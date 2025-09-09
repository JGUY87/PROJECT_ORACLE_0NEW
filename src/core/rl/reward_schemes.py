# src/core/rl/reward_schemes.py
# -*- coding: utf-8 -*-
"""
리워드 스킴 v2.3 (일일 손실컷·슬리피지·펀딩비 내재화)
- 기본 보상: (수익 - 비용 - 리스크 - 홀드 - 과매매) + 잠재기반 shaping(Φ_t - γΦ_{t-1})
- 확장 항목: 
  * 슬리피지(체결가-예상가) → bps 기준 패널티
  * 펀딩비(8h 기준 funding_rate) → step 시간 비율 반영
  * 일일 손실컷(누적 PnL vs MAX_DAILY_LOSS) → 소프트 장벽(soft barrier) 페널티
안전장치:
  - NaN/Inf 방지, tanh 스케일링 + 클리핑
  - 컨텍스트 값이 없으면 0으로 처리(과도한 패널티 없음)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Callable, Any
import math

# ─────────────────────────────────────────────────────────
# 안전 유틸
# ─────────────────────────────────────────────────────────
def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isfinite(v):
            return v
    except Exception:
        pass
    return float(default)

def _clip(x: float, lo: float, hi: float) -> float:
    if x < lo: return lo
    if x > hi: return hi
    return x

def _softplus(x: float) -> float:
    # 안정적인 softplus
    if x > 50:  # overflow 보호
        return x
    if x < -50:
        return 0.0
    return math.log1p(math.exp(x))

# ─────────────────────────────────────────────────────────
# 가중치/컨텍스트
# ─────────────────────────────────────────────────────────
@dataclass
class RewardWeights:
    pnl: float = 1.0                 # 미실현 포함 PnL 가중
    realized: float = 0.5            # 실현 PnL 가중
    cost: float = 1.0                # 거래 비용(수수료/슬리피지/펀딩 외 일반 비용) 페널티
    risk: float = 0.5                # 레버리지/변동성/드로우다운 페널티
    hold: float = 0.0                # 과도 보유 페널티
    churn: float = 0.2               # 과매매(짧은 뒤집기/빈번한 트레이드) 페널티
    # v2.3 확장
    slip: float = 0.6                # 슬리피지(bps) 페널티 가중
    funding: float = 0.4             # 펀딩비 페널티 가중
    loss_cut: float = 2.0            # 일일 손실컷 장벽 가중(강하게)
    drawdown: float = 0.3            # 일중 드로우다운(%) 페널티
    profile: float = 0.3             # 프로파일 shaping 가중
    scale: float = 1.0               # 최종 스케일

@dataclass
class ShapingContext:
    # 거래/포지션 정보
    side: int = 0                        # -1(short), 0(flat), 1(long)
    position_value: float = 0.0          # USDT 등 평가액(참고용)
    pos_age_bars: int = 0
    flip: int = 0                        # 직전 바에서 방향 전환했는가
    atr_pct: float = math.nan            # ATR/가격 (%)

    # 기술지표(옵션)
    ema20: float = math.nan
    ema50: float = math.nan
    rsi14: float = math.nan
    td_up: float = 0.0
    td_down: float = 0.0
    bb_width: float = math.nan
    vol_spike: float = math.nan
    mom_5: float = 0.0
    mom_60: float = 0.0
    ha_up: int = 0

    # v2.3 확장 입력
    # 슬리피지: (체결가-예상가)/예상가 * 1e4 (bps). 미제공시 아래 expected/fill로 계산 시도
    slippage_bps: float = math.nan
    expected_price: float = math.nan
    fill_price: float = math.nan

    # 펀딩: 8시간 기준 funding_rate (예: 0.01 = +1%) + step_minutes
    funding_rate_8h: float = math.nan
    step_minutes: float = 1.0

    # 일일 손익/제한
    daily_pnl_usdt: float = 0.0
    daily_loss_limit_usdt: float = 0.0
    daily_drawdown_pct: float = math.nan  # 당일 고점 대비 하락 % (예: 3.5)

    # 임의 피처
    features: Dict[str, float] = field(default_factory=dict)

# ─────────────────────────────────────────────────────────
# 잠재기반 shaping(Φ)
# ─────────────────────────────────────────────────────────
def potential_snake_ma(ctx: ShapingContext) -> float:
    e20, e50 = _f(ctx.ema20, 0), _f(ctx.ema50, 0)
    if e20 == 0 and e50 == 0:
        return 0.0
    align_up = (e20 > e50 and ctx.side >= 0)
    align_dn = (e20 < e50 and ctx.side <= 0)
    return 0.5 if (align_up or align_dn) else -0.2

def potential_wonyotti(ctx: ShapingContext) -> float:
    r = _f(ctx.rsi14, 50)
    if ctx.side > 0 and r <= 35: return 0.5
    if ctx.side < 0 and r >= 65: return 0.5
    return -0.1

def potential_td_mark(ctx: ShapingContext) -> float:
    if _f(ctx.td_up) >= 8 and ctx.side > 0: return 0.4
    if _f(ctx.td_down) >= 8 and ctx.side < 0: return 0.4
    return 0.0

def potential_smart_money(ctx: ShapingContext) -> float:
    bw = _f(ctx.bb_width, 1.0)
    vs = _f(ctx.vol_spike, 1.0)
    if bw < 0.03 and vs > 1.5:
        pref = 1 if int(ctx.ha_up)==1 else -1
        return 0.4 if ctx.side==pref else -0.1
    return 0.0

def potential_hukwoonyam(ctx: ShapingContext) -> float:
    s = _f(ctx.mom_5) + _f(ctx.mom_60)
    if s > 0 and ctx.side > 0: return 0.3
    if s < 0 and ctx.side < 0: return 0.3
    return 0.0

POTENTIALS: Dict[str, Callable[[ShapingContext], float]] = {
    "snake_ma": potential_snake_ma,
    "wonyotti": potential_wonyotti,
    "td_mark": potential_td_mark,
    "smart_money_accumulation": potential_smart_money,
    "hukwoonyam": potential_hukwoonyam,
}

# ─────────────────────────────────────────────────────────
# 확장 페널티 계산
# ─────────────────────────────────────────────────────────
def _slippage_bps(ctx: ShapingContext) -> float:
    bps = _f(ctx.slippage_bps, math.nan)
    if math.isnan(bps):
        exp_p = _f(ctx.expected_price, math.nan)
        fill_p = _f(ctx.fill_price, math.nan)
        if math.isfinite(exp_p) and exp_p > 0 and math.isfinite(fill_p):
            bps = abs((fill_p - exp_p) / exp_p) * 1e4
        else:
            bps = 0.0
    return max(0.0, bps)

def _funding_pay_pct(ctx: ShapingContext) -> float:
    """이 스텝에서 '지불하는' 펀딩 비율(%)을 근사.
    - 8h 기준 funding_rate_8h 사용, 스텝 시간(step_minutes) 비율 반영
    - Long은 rate>0일 때 지불, Short는 rate<0일 때 지불
    반환 예: 0.005(%)
    """
    rate8 = _f(ctx.funding_rate_8h, math.nan)
    if not math.isfinite(rate8) or rate8 == 0:
        return 0.0
    step_h = max(0.0, _f(ctx.step_minutes, 1.0) / 60.0)
    pay = 0.0
    if ctx.side > 0 and rate8 > 0:
        pay = rate8 * (step_h / 8.0) * 100  # %
    elif ctx.side < 0 and rate8 < 0:
        pay = abs(rate8) * (step_h / 8.0) * 100  # %
    return max(0.0, pay)

def _daily_loss_barrier(ctx: ShapingContext) -> float:
    """일일 손실컷 소프트 장벽. 한계를 넘기 전에도 접근 시 점증적 페널티.
    반환값: 0 이상(무단위), ~0이면 영향 적음, 커질수록 강한 페널티.
    """
    limit = _f(ctx.daily_loss_limit_usdt, 0.0)
    if limit <= 0:
        return 0.0
    pnl = _f(ctx.daily_pnl_usdt, 0.0)  # 음수면 손실
    # 손실 비율 r = (-pnl)/limit (>=0)
    r = max(0.0, -pnl / max(1e-9, limit))
    # r<1 구간에서도 완만히 증가, r>=1에서 급격히 증가하는 softplus 곡선
    return _softplus(r - 0.7)  # 70% 소진 구간부터 가속

# ─────────────────────────────────────────────────────────
# 메인 리워드
# ─────────────────────────────────────────────────────────
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
    clip: float = 1.0,
    tanh_scale: float = 1.0,
) -> Tuple[float, float]:
    """반환: (총보상, 현재 잠재값Φ)
    총보상 = 기본(수익-비용-리스크-홀드-과매매-슬리피지-펀딩-손실컷-드로우다운) + shaping(Φ_t - γΦ_{t-1})
    """
    # 1) 기본 항목
    d_equity = _f(delta_equity)
    r_real   = _f(realized_pnl)
    c_cost   = abs(_f(costs))
    r_risk   = abs(_f(risk_penalty))
    r_hold   = abs(_f(hold_penalty))

    # 2) 컨텍스트 기반 확장 항목
    churn_pen = 0.0
    slip_pen  = 0.0
    fund_pen  = 0.0
    loss_bar  = 0.0
    dd_pen    = 0.0

    if ctx is not None:
        # 과매매
        flip = int(_f(ctx.flip, 0)); age = max(0, int(_f(ctx.pos_age_bars, 0)))
        if flip == 1 and age <= 2: churn_pen = 1.0
        elif age <= 1: churn_pen = 0.5

        # 슬리피지(bps → 무차원 페널티; 10bp=0.001 → 0.1%)
        bps = _slippage_bps(ctx)  # ex: 12.3
        slip_pen = bps / 10000.0  # 비율

        # 펀딩(지불분만 %, ex: 0.005%)
        fund_pct = _funding_pay_pct(ctx) / 100.0
        fund_pen = fund_pct

        # 일일 손실컷 소프트 장벽
        loss_bar = _daily_loss_barrier(ctx)

        # 일중 드로우다운(%) 페널티
        dd_pct = _f(ctx.daily_drawdown_pct, math.nan)
        if math.isfinite(dd_pct) and dd_pct > 0:
            dd_pen = dd_pct / 100.0  # 5% → 0.05

    # 3) 기본 보상
    base = (
        weights.pnl      * d_equity +
        weights.realized * r_real   -
        weights.cost     * c_cost   -
        weights.risk     * r_risk   -
        weights.hold     * r_hold   -
        weights.churn    * churn_pen -
        weights.slip     * slip_pen  -
        weights.funding  * fund_pen  -
        weights.loss_cut * loss_bar  -
        weights.drawdown * dd_pen
    )

    # 4) shaping
    if ctx is None or weights.profile <= 0:
        shaped = base; phi = 0.0
    else:
        pot_fn = POTENTIALS.get(profile, lambda *_: 0.0)
        phi = float(pot_fn(ctx))
        gamma = _clip(float(gamma), 0.0, 0.999)
        shaped = base + weights.profile * (phi - gamma * _f(last_potential))

    # 5) 후처리
    shaped *= float(weights.scale or 1.0)
    if tanh_scale and tanh_scale > 0:
        shaped = math.tanh(shaped * float(tanh_scale))
    if clip and clip > 0:
        shaped = _clip(shaped, -abs(clip), +abs(clip))

    return float(shaped), float(phi)

# ─────────────────────────────────────────────────────────
# 프리셋(권장값)
# ─────────────────────────────────────────────────────────
PRESETS: Dict[str, RewardWeights] = {
    "snake_ma": RewardWeights(pnl=1.0, realized=0.4, cost=0.9, risk=0.4, hold=0.2, churn=0.2, slip=0.6, funding=0.3, loss_cut=2.0, drawdown=0.25, profile=0.4, scale=1.0),
    "wonyotti": RewardWeights(pnl=1.0, realized=0.5, cost=1.1, risk=0.6, hold=0.1, churn=0.3, slip=0.7, funding=0.4, loss_cut=2.2, drawdown=0.3, profile=0.35, scale=1.0),
    "td_mark": RewardWeights(pnl=1.0, realized=0.5, cost=1.0, risk=0.5, hold=0.1, churn=0.35, slip=0.7, funding=0.3, loss_cut=2.0, drawdown=0.3, profile=0.35, scale=1.0),
    "smart_money_accumulation": RewardWeights(pnl=1.0, realized=0.5, cost=1.1, risk=0.5, hold=0.1, churn=0.25, slip=0.6, funding=0.35, loss_cut=2.0, drawdown=0.25, profile=0.4, scale=1.0),
    "hukwoonyam": RewardWeights(pnl=1.0, realized=0.4, cost=1.0, risk=0.5, hold=0.05, churn=0.2, slip=0.6, funding=0.3, loss_cut=2.0, drawdown=0.25, profile=0.3, scale=1.0),
}

def get_preset(profile: str) -> RewardWeights:
    return PRESETS.get(profile, RewardWeights())

# ─────────────────────────────────────────────────────────
# 자체 테스트
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    w = get_preset("snake_ma")
    ctx = ShapingContext(
        ema20=101, ema50=100, side=1, pos_age_bars=3, flip=0,
        slippage_bps=12.0, funding_rate_8h=0.01, step_minutes=1.0,
        daily_pnl_usdt=-150.0, daily_loss_limit_usdt=200.0, daily_drawdown_pct=2.5
    )
    r, phi = compute_reward(
        w, delta_equity=5.0, realized_pnl=0.0, costs=0.8, risk_penalty=1.2, hold_penalty=0.0,
        profile="snake_ma", ctx=ctx, gamma=0.99, last_potential=0.3, clip=1.0, tanh_scale=0.3
    )
    print("reward=", r, "phi=", phi)
