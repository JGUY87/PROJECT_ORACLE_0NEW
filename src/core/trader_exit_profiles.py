# -*- coding: utf-8 -*-
"""전략별 청산 파라미터 템플릿을 정의합니다."""
from dataclasses import dataclass
from typing import Dict

@dataclass
class ExitProfile:
    """거래 전략별 청산 파라미터를 정의하는 데이터 클래스."""
    name: str  # 전략 이름
    tp1_r: float = 1.0  # 1차 익절 목표 (Risk 대비 수익률)
    tp1_pct: float = 0.33  # 1차 익절 시 청산할 포지션 비율
    tp2_r: float = 2.0  # 2차 익절 목표 (Risk 대비 수익률)
    tp2_pct: float = 0.33  # 2차 익절 시 청산할 포지션 비율
    runner_pct: float = 0.34  # 러너 포지션 비율 (1 - tp1_pct - tp2_pct)
    trail_atr_mult: float = 2.5  # 트레일링 스톱 ATR 배수
    trail_ema_span: int = 20  # 트레일링 스톱 EMA 기간
    sl_atr_mult: float = 1.5  # 손절 ATR 배수
    daily_loss_cut_pct: float = 0.07  # 일일 손실 제한 비율 (미사용)
    use_heikin_color_exit: bool = False  # 헤이킨 아시 색상 변경 시 청산 사용 여부
    use_ema_cross_exit: bool = False  # EMA 교차 시 청산 사용 여부
    use_vwap_target: bool = False  # VWAP 목표 사용 여부
    use_td_exhaustion: bool = False  # TD 시퀀스 소진 시 청산 사용 여부

# 사전 정의된 전략 프로필들
PROFILES: Dict[str, ExitProfile] = {
    "hukwoonyam": ExitProfile(name="hukwoonyam", tp1_r=1.2, tp2_r=2.2, trail_atr_mult=2.8, sl_atr_mult=1.6),
    "wonyotti": ExitProfile(name="wonyotti", tp1_r=1.0, tp2_r=1.8, trail_atr_mult=2.2, sl_atr_mult=1.4, use_heikin_color_exit=True),
    "td_mark": ExitProfile(name="td_mark", tp1_r=1.3, tp2_r=2.6, trail_atr_mult=2.5, sl_atr_mult=1.5, use_td_exhaustion=True),
    "volume_pullback": ExitProfile(name="volume_pullback", tp1_r=1.0, tp2_r=2.0, trail_atr_mult=2.0, sl_atr_mult=1.4, use_vwap_target=True),
    "smart_money_accumulation": ExitProfile(name="smart_money_accumulation", tp1_r=1.2, tp2_r=2.4, runner_pct=0.5, tp1_pct=0.25, tp2_pct=0.25, trail_atr_mult=2.7, sl_atr_mult=1.6),
    "snake_ma": ExitProfile(name="snake_ma", tp1_r=1.1, tp2_r=2.0, trail_atr_mult=2.3, sl_atr_mult=1.5, use_ema_cross_exit=True),
}