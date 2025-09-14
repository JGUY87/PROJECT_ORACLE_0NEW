# tests/backtest/test_runner.py
# -*- coding: utf-8 -*-
"""
src.backtest.runner의 데이터 캐싱 기능에 대한 단위 테스트
"""
import unittest
import os
import pandas as pd
from unittest.mock import patch, AsyncMock
import asyncio
import sys

# 프로젝트 루트를 sys.path에 추가
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.backtest.runner import get_ohlcv_data, CACHE_DIR

class TestBacktestRunnerCaching(unittest.TestCase):

    def setUp(self):
        """테스트 실행 전, 테스트용 캐시 파일 경로 설정 및 디렉토리 생성"""
        self.symbol = "TEST/USDT"
        self.start_date = "2023-01-01"
        safe_symbol = self.symbol.replace('/', '_')
        self.cache_filename = f"{safe_symbol}_1d_{self.start_date.split('-')[0]}.csv"
        self.cache_filepath = CACHE_DIR / self.cache_filename
        
        # 테스트 실행 전 혹시 모를 캐시 파일 삭제
        if os.path.exists(self.cache_filepath):
            os.remove(self.cache_filepath)

    def tearDown(self):
        """테스트 실행 후, 생성된 캐시 파일 삭제"""
        if os.path.exists(self.cache_filepath):
            os.remove(self.cache_filepath)

    @patch('src.backtest.runner.get_exchange_client')
    def test_caching_logic(self, mock_get_client):
        """
        캐싱 로직 테스트:
        1. 캐시 없을 때: API 호출하고, CSV 파일 생성하는지 확인
        2. 캐시 있을 때: API 호출 안 하고, CSV 파일 읽어오는지 확인
        """
        # --- 1. 캐시 파일이 없을 때 ---
        
        # Mock 객체 설정: fetch_ohlcv가 테스트용 데이터프레임을 반환하도록 설정
        mock_client = AsyncMock()
        mock_client.parse8601.return_value = 'mock_since'
        mock_ohlcv = [
            [pd.to_datetime('2023-05-01').value // 10**6, 100, 110, 90, 105, 1000],
            [pd.to_datetime('2023-05-02').value // 10**6, 105, 115, 95, 110, 1200],
        ]
        mock_client.fetch_ohlcv.return_value = mock_ohlcv
        mock_get_client.return_value = mock_client

        # get_ohlcv_data 실행 (비동기 함수 실행)
        df1 = asyncio.run(get_ohlcv_data(self.symbol, self.start_date))

        # 검증 (1): API가 호출되었는지 확인
        mock_get_client.assert_called_once()
        mock_client.fetch_ohlcv.assert_called_once()
        
        # 검증 (2): 캐시 파일이 생성되었는지 확인
        self.assertTrue(os.path.exists(self.cache_filepath))
        
        # 검증 (3): 반환된 데이터프레임이 올바른지 확인
        self.assertIsInstance(df1, pd.DataFrame)
        self.assertEqual(len(df1), 2)
        self.assertEqual(df1.iloc[0]['close'], 105)

        # --- 2. 캐시 파일이 있을 때 ---
        
        # Mock 객체 리셋 (다시 호출되지 않아야 함)
        mock_get_client.reset_mock()
        mock_client.fetch_ohlcv.reset_mock()

        # get_ohlcv_data 다시 실행
        df2 = asyncio.run(get_ohlcv_data(self.symbol, self.start_date))

        # 검증 (4): API가 호출되지 않았는지 확인
        mock_get_client.assert_not_called()
        mock_client.fetch_ohlcv.assert_not_called()

        # 검증 (5): 반환된 데이터프레임이 첫 번째와 동일한지 확인
        self.assertTrue(df1.equals(df2))
        self.assertEqual(df2.iloc[1]['close'], 110)

if __name__ == '__main__':
    unittest.main()
