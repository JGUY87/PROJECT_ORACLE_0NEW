# tests/core/test_strategy_recommender.py
# -*- coding: utf-8 -*-
"""
src.core.strategy_recommender에 대한 단위 테스트
"""
import unittest
import os
import json
import sys

# 프로젝트 루트를 sys.path에 추가
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.strategy_recommender import choose_strategy, choose_action, ai_recommend_strategy_live

class TestStrategyRecommender(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """테스트 클래스 설정: 기본 파라미터 로드"""
        try:
            config_path = os.path.join(project_root, 'configs', 'strategy_params.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                cls.params = json.load(f)
        except Exception as e:
            print(f"테스트 설정 중 에러: strategy_params.json 로드 실패 - {e}")
            cls.params = {}

    def test_choose_strategy(self):
        """choose_strategy 함수가 주어진 피처에 따라 올바른 전략을 반환하는지 테스트"""
        
        # 1. PPO 점수가 높을 때 'hukwoonyam' 전략 선택
        features_ppo = {"ppo_score": 0.9}
        strategy, reason, _ = choose_strategy(features_ppo)
        self.assertEqual(strategy, "hukwoonyam")
        self.assertEqual(reason, "PPO 강화")

        # 2. 하락장 + 과매도 + 거래량 급등 시 'wonyotti' 전략 선택
        features_wonyotti = {"is_downtrend": True, "vol_spike": 1.5, "rsi": 25}
        strategy, _, _ = choose_strategy(features_wonyotti)
        self.assertEqual(strategy, "wonyotti")

        # 3. 명확한 신호가 없을 때 기본 'snake_ma' 전략 선택
        features_default = {"rsi": 50, "momentum": 0}
        strategy, _, _ = choose_strategy(features_default)
        self.assertEqual(strategy, "snake_ma")

    def test_choose_action(self):
        """choose_action 함수가 주어진 피처에 따라 올바른 액션을 반환하는지 테스트"""

        # 1. 강한 매수 신호 (골든크로스, 모멘텀 상승)
        features_buy = {"golden_cross": 1, "momentum": 0.5, "rsi": 40, "stoch_k": 25}
        action, confidence = choose_action(features_buy)
        self.assertEqual(action, "buy")
        self.assertGreater(confidence, 0)

        # 2. 강한 매도 신호 (데드크로스, 모멘텀 하락)
        features_sell = {"dead_cross": 1, "momentum": -0.5, "rsi": 60, "stoch_k": 75, "is_downtrend": True}
        action, confidence = choose_action(features_sell)
        self.assertEqual(action, "sell")
        self.assertGreater(confidence, 0)

        # 3. 중립(HOLD) 신호
        features_hold = {"golden_cross": 0, "dead_cross": 0, "momentum": 0, "rsi": 50, "stoch_k": 50}
        action, confidence = choose_action(features_hold)
        self.assertEqual(action, "hold")
        self.assertEqual(confidence, 0.0)
        
        # 4. 매수/매도 신호가 약하거나 상충될 때 HOLD
        features_conflicting = {"golden_cross": 1, "dead_cross": 1} # 상충
        action, _ = choose_action(features_conflicting)
        self.assertEqual(action, "hold")

    def test_ai_recommend_strategy_live(self):
        """메인 함수가 입력을 올바르게 처리하고 완전한 추천을 반환하는지 테스트"""

        # 1. 단일 피처 입력
        features = {"symbol": "BTC/USDT", "features": {"golden_cross": 1, "momentum": 0.5}}
        recommendation = ai_recommend_strategy_live(**features)
        self.assertEqual(recommendation["symbol"], "BTC/USDT")
        self.assertEqual(recommendation["action"], "buy")
        self.assertIn("strategy", recommendation)
        self.assertIn("reason", recommendation)

        # 2. 피처 입력이 없을 때 기본 'hold' 추천
        recommendation_no_features = ai_recommend_strategy_live(symbol="ETH/USDT")
        self.assertEqual(recommendation_no_features["symbol"], "ETH/USDT")
        self.assertEqual(recommendation_no_features["action"], "hold")
        self.assertEqual(recommendation_no_features["confidence"], 0.0)

if __name__ == '__main__':
    unittest.main()
