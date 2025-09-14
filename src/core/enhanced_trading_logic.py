# -*- coding: utf-8 -*-
"""
향상된 심볼 선정 및 AI 추론 최적화 모듈

- 목적: 거래 성능 향상을 위한 스마트 심볼 선정 및 AI 추론 최적화
- 핵심 기능:
  1) 동적 심볼 스코링: 변동성, 거래량, 유동성을 종합한 점수 시스템
  2) 시장 상황 인식: 불안정한 시장에서 안전한 심볼 우선 선택
  3) AI 추론 결과 후처리: 신뢰도 기반 필터링 및 리스크 조절
  4) 성과 추적: 과거 거래 결과를 바탕으로 한 학습 시스템
"""
from __future__ import annotations
import logging
import time
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from collections import deque, defaultdict
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class SymbolMetrics:
    """심볼별 평가 지표"""
    symbol: str
    volume_score: float      # 거래량 점수 (0-100)
    volatility_score: float  # 변동성 점수 (0-100)
    liquidity_score: float   # 유동성 점수 (0-100)
    momentum_score: float    # 모멘텀 점수 (-100 to 100)
    risk_score: float        # 리스크 점수 (0-100, 낮을수록 안전)
    total_score: float       # 종합 점수 (0-500)
    market_cap_rank: int = 0 # 시가총액 순위 (1이 가장 높음)

@dataclass
class TradeResult:
    """거래 결과 추적"""
    symbol: str
    timestamp: datetime
    action: str
    confidence: float
    entry_price: float
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    duration_hours: Optional[float] = None

class SmartSymbolSelector:
    """스마트 심볼 선정기"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.trade_history: deque = deque(maxlen=max_history)
        self.symbol_performance: defaultdict = defaultdict(lambda: {"wins": 0, "losses": 0, "avg_pnl": 0.0})
        
        # 시장 상황별 가중치 (변동적)
        self.weights = {
            "stable": {"volume": 0.3, "volatility": 0.2, "liquidity": 0.25, "momentum": 0.15, "risk": 0.1},
            "volatile": {"volume": 0.2, "volatility": 0.15, "liquidity": 0.35, "momentum": 0.2, "risk": 0.1},
            "trending": {"volume": 0.25, "volatility": 0.3, "liquidity": 0.2, "momentum": 0.25, "risk": 0.0}
        }
        
    def analyze_symbols(self, market_data: Dict[str, Any]) -> List[SymbolMetrics]:
        """시장 데이터를 분석하여 심볼별 메트릭 생성"""
        symbol_metrics = []
        
        # 전체 시장 통계 계산
        volumes = [data.get('volume_usd', 0) for data in market_data.values()]
        price_changes = [data.get('price_change_pct', 0) for data in market_data.values()]
        
        if not volumes or not price_changes:
            return symbol_metrics
            
        volume_median = np.median(volumes)
        volume_std = np.std(volumes)
        volatility_median = np.median([abs(pc) for pc in price_changes])
        
        for symbol, data in market_data.items():
            try:
                # 기본 지표 추출
                volume_usd = data.get('volume_usd', 0)
                price_change_pct = data.get('price_change_pct', 0)
                last_price = data.get('last_price', 0)
                
                # 점수 계산
                volume_score = min(100, (volume_usd / (volume_median + 1e-12)) * 50)
                volatility_score = min(100, (abs(price_change_pct) / (volatility_median + 1e-12)) * 50)
                liquidity_score = self._calculate_liquidity_score(data)
                momentum_score = max(-100, min(100, price_change_pct * 10))  # -100~100 범위
                risk_score = self._calculate_risk_score(symbol, data)
                
                # 시가총액 기반 순위 (주요 코인 우선)
                market_cap_rank = self._get_market_cap_rank(symbol)
                
                # 종합 점수 계산
                total_score = (
                    volume_score + volatility_score + liquidity_score + 
                    abs(momentum_score) - risk_score
                ) + (100 - market_cap_rank) * 0.1  # 시가총액 보너스
                
                metrics = SymbolMetrics(
                    symbol=symbol,
                    volume_score=volume_score,
                    volatility_score=volatility_score,
                    liquidity_score=liquidity_score,
                    momentum_score=momentum_score,
                    risk_score=risk_score,
                    total_score=total_score,
                    market_cap_rank=market_cap_rank
                )
                
                symbol_metrics.append(metrics)
                
            except Exception as e:
                logger.warning(f"심볼 {symbol} 분석 중 오류: {e}")
                continue
        
        # 종합 점수순으로 정렬
        symbol_metrics.sort(key=lambda x: x.total_score, reverse=True)
        return symbol_metrics
    
    def _calculate_liquidity_score(self, data: Dict) -> float:
        """유동성 점수 계산"""
        try:
            ticker = data.get('ticker', {})
            bid = ticker.get('bid', 0)
            ask = ticker.get('ask', 0)
            
            if bid > 0 and ask > 0:
                spread = (ask - bid) / ((ask + bid) / 2) * 100
                # 스프레드가 낮을수록 높은 점수
                liquidity_score = max(0, 100 - spread * 50)
            else:
                liquidity_score = 50  # 기본값
                
            return min(100, liquidity_score)
            
        except Exception:
            return 50
    
    def _calculate_risk_score(self, symbol: str, data: Dict) -> float:
        """리스크 점수 계산 (낮을수록 안전)"""
        try:
            risk_score = 0
            
            # 가격 변동성 리스크
            price_change = abs(data.get('price_change_pct', 0))
            if price_change > 10:
                risk_score += 40
            elif price_change > 5:
                risk_score += 20
            elif price_change > 2:
                risk_score += 10
            
            # 과거 성과 기반 리스크
            perf = self.symbol_performance[symbol]
            if perf["wins"] + perf["losses"] > 0:
                win_rate = perf["wins"] / (perf["wins"] + perf["losses"])
                if win_rate < 0.3:
                    risk_score += 30
                elif win_rate < 0.5:
                    risk_score += 15
            
            # 알트코인 리스크 (BTC, ETH 이외)
            if symbol not in ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BTCUSDT', 'ETHUSDT']:
                risk_score += 10
            
            return min(100, risk_score)
            
        except Exception:
            return 50
    
    def _get_market_cap_rank(self, symbol: str) -> int:
        """시가총액 기반 순위 (간소화된 버전)"""
        # 주요 코인들의 대략적인 순위
        major_coins = {
            'BTC/USDT:USDT': 1, 'BTCUSDT': 1,
            'ETH/USDT:USDT': 2, 'ETHUSDT': 2,
            'BNB/USDT:USDT': 3, 'BNBUSDT': 3,
            'ADA/USDT:USDT': 4, 'ADAUSDT': 4,
            'XRP/USDT:USDT': 5, 'XRPUSDT': 5,
            'SOL/USDT:USDT': 6, 'SOLUSDT': 6,
            'DOT/USDT:USDT': 7, 'DOTUSDT': 7,
            'MATIC/USDT:USDT': 8, 'MATICUSDT': 8,
            'AVAX/USDT:USDT': 9, 'AVAXUSDT': 9,
            'LINK/USDT:USDT': 10, 'LINKUSDT': 10
        }
        
        return major_coins.get(symbol, 50)
    
    def select_top_symbols(self, 
                          market_data: Dict[str, Any], 
                          top_n: int = 3,
                          market_condition: str = "stable") -> List[str]:
        """시장 상황을 고려한 상위 심볼 선정"""
        
        # 심볼 분석
        symbol_metrics = self.analyze_symbols(market_data)
        
        if not symbol_metrics:
            return []
        
        # 시장 상황별 필터링
        filtered_symbols = self._filter_by_market_condition(symbol_metrics, market_condition)
        
        # 상위 N개 선정
        top_symbols = [metrics.symbol for metrics in filtered_symbols[:top_n]]
        
        logger.info(f"[{market_condition} 시장] 선정된 상위 {len(top_symbols)}개 심볼: {top_symbols}")
        
        # 선정 이유 로깅
        for i, metrics in enumerate(filtered_symbols[:top_n]):
            logger.info(f"  {i+1}. {metrics.symbol}: 종합점수 {metrics.total_score:.1f} "
                       f"(거래량:{metrics.volume_score:.0f}, 변동성:{metrics.volatility_score:.0f}, "
                       f"유동성:{metrics.liquidity_score:.0f}, 모멘텀:{metrics.momentum_score:.0f}, "
                       f"리스크:{metrics.risk_score:.0f})")
        
        return top_symbols
    
    def _filter_by_market_condition(self, 
                                   symbol_metrics: List[SymbolMetrics], 
                                   market_condition: str) -> List[SymbolMetrics]:
        """시장 상황별 심볼 필터링"""
        
        if market_condition == "volatile":
            # 변동성이 큰 시장: 안전한 심볼 우선, 높은 유동성 필요
            return [s for s in symbol_metrics if s.risk_score < 60 and s.liquidity_score > 40]
            
        elif market_condition == "trending":
            # 추세장: 모멘텀이 강한 심볼 우선
            return [s for s in symbol_metrics if abs(s.momentum_score) > 30]
            
        else:  # stable
            # 안정적 시장: 균형 잡힌 선택
            return symbol_metrics
    
    def detect_market_condition(self, market_data: Dict[str, Any]) -> str:
        """시장 상황 자동 감지"""
        try:
            price_changes = [data.get('price_change_pct', 0) for data in market_data.values()]
            
            if not price_changes:
                return "stable"
            
            volatility = np.std(price_changes)
            avg_change = np.mean([abs(pc) for pc in price_changes])
            trend_strength = abs(np.mean(price_changes))
            
            if volatility > 8 or avg_change > 6:
                return "volatile"
            elif trend_strength > 3 and volatility > 2:
                return "trending"
            else:
                return "stable"
                
        except Exception:
            return "stable"
    
    def record_trade_result(self, result: TradeResult):
        """거래 결과 기록"""
        self.trade_history.append(result)
        
        # 성과 통계 업데이트
        if result.pnl is not None:
            perf = self.symbol_performance[result.symbol]
            if result.pnl > 0:
                perf["wins"] += 1
            else:
                perf["losses"] += 1
            
            # 평균 PnL 업데이트
            total_trades = perf["wins"] + perf["losses"]
            perf["avg_pnl"] = ((perf["avg_pnl"] * (total_trades - 1)) + result.pnl) / total_trades
    
    def get_performance_report(self) -> Dict[str, Any]:
        """성과 리포트 생성"""
        if not self.trade_history:
            return {"total_trades": 0}
        
        recent_trades = list(self.trade_history)[-50:]  # 최근 50개 거래
        
        total_pnl = sum(t.pnl for t in recent_trades if t.pnl is not None)
        wins = sum(1 for t in recent_trades if t.pnl is not None and t.pnl > 0)
        losses = len([t for t in recent_trades if t.pnl is not None]) - wins
        
        return {
            "total_trades": len(recent_trades),
            "win_rate": wins / (wins + losses) if (wins + losses) > 0 else 0,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / len(recent_trades) if recent_trades else 0,
            "best_symbols": dict(sorted(self.symbol_performance.items(), 
                                      key=lambda x: x[1]["avg_pnl"], reverse=True)[:5])
        }

class EnhancedAIFilter:
    """AI 추론 결과 향상 필터"""
    
    def __init__(self):
        self.confidence_threshold = 0.6  # 최소 신뢰도
        self.recent_predictions = deque(maxlen=100)
        
    def filter_ai_recommendation(self, 
                                recommendation: Dict[str, Any], 
                                market_condition: str = "stable") -> Optional[Dict[str, Any]]:
        """AI 추천 결과 필터링 및 향상"""
        
        if not recommendation or recommendation.get('action') == 'hold':
            return None
        
        confidence = recommendation.get('confidence', 0)
        action = recommendation.get('action', 'hold')
        
        # 기본 신뢰도 필터
        adjusted_threshold = self._get_adjusted_threshold(market_condition)
        if confidence < adjusted_threshold:
            logger.info(f"신뢰도 부족으로 거래 제외: {confidence:.3f} < {adjusted_threshold:.3f}")
            return None
        
        # 시장 상황별 추가 검증
        if not self._validate_for_market_condition(recommendation, market_condition):
            return None
        
        # 과거 성과 기반 조정
        adjusted_recommendation = self._adjust_based_on_history(recommendation)
        
        # 추천 기록
        self.recent_predictions.append({
            'timestamp': time.time(),
            'symbol': recommendation.get('symbol'),
            'action': action,
            'confidence': confidence,
            'market_condition': market_condition
        })
        
        return adjusted_recommendation
    
    def _get_adjusted_threshold(self, market_condition: str) -> float:
        """시장 상황별 조정된 신뢰도 임계값"""
        thresholds = {
            "volatile": 0.75,  # 변동성 시장에서는 더 높은 신뢰도 요구
            "trending": 0.55,  # 추세장에서는 다소 낮은 신뢰도도 허용
            "stable": 0.65     # 안정적 시장에서는 중간 수준
        }
        return thresholds.get(market_condition, self.confidence_threshold)
    
    def _validate_for_market_condition(self, 
                                     recommendation: Dict[str, Any], 
                                     market_condition: str) -> bool:
        """시장 상황별 추가 검증"""
        
        confidence = recommendation.get('confidence', 0)
        
        if market_condition == "volatile":
            # 변동성 시장: 매우 높은 신뢰도만 허용
            return confidence > 0.8
            
        elif market_condition == "trending":
            # 추세장: 방향이 맞다면 낮은 신뢰도도 허용
            return confidence > 0.5
            
        else:  # stable
            # 안정적 시장: 중간 수준의 신뢰도
            return confidence > 0.6
    
    def _adjust_based_on_history(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        """과거 성과를 바탕으로 추천 조정"""
        # 현재는 단순히 원본 반환, 추후 학습 로직 추가 가능
        return recommendation.copy()
    
    def get_prediction_accuracy(self) -> float:
        """예측 정확도 계산 (단순화된 버전)"""
        if len(self.recent_predictions) < 10:
            return 0.0
        
        # 실제로는 거래 결과와 비교해야 하지만, 여기서는 신뢰도 기반 추정
        high_confidence_predictions = [
            p for p in self.recent_predictions 
            if p.get('confidence', 0) > 0.7
        ]
        
        return len(high_confidence_predictions) / len(self.recent_predictions)

# 전역 인스턴스
_symbol_selector: Optional[SmartSymbolSelector] = None
_ai_filter: Optional[EnhancedAIFilter] = None

def get_smart_symbol_selector() -> SmartSymbolSelector:
    """스마트 심볼 선정기 인스턴스 반환"""
    global _symbol_selector
    if _symbol_selector is None:
        _symbol_selector = SmartSymbolSelector()
    return _symbol_selector

def get_enhanced_ai_filter() -> EnhancedAIFilter:
    """향상된 AI 필터 인스턴스 반환"""
    global _ai_filter
    if _ai_filter is None:
        _ai_filter = EnhancedAIFilter()
    return _ai_filter