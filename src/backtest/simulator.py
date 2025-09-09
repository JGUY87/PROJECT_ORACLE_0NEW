# -*- coding: utf-8 -*-
"""간단한 루프 기반 백테스팅 시뮬레이터."""
from __future__ import annotations
from typing import Dict, Any, List
import pandas as pd

def run_simple_backtest(
    price_data: pd.Series,
    fast_ma: int = 10,
    slow_ma: int = 30,
    initial_cash: float = 10000.0,
    fee_bps: float = 2.0
) -> Dict[str, Any]:
    """
    간단한 이동평균 교차 전략으로 루프 기반 백테스트를 실행합니다.

    Args:
        price_data (pd.Series): 시계열 가격 데이터 (인덱스는 타임스탬프).
        fast_ma (int): 단기 이동평균 기간.
        slow_ma (int): 장기 이동평균 기간.
        initial_cash (float): 초기 자본금.
        fee_bps (float): 거래 수수료 (basis points, 1bps = 0.01%).

    Returns:
        Dict[str, Any]: 백테스트 결과 요약.
    """
    # 1. 지표 계산
    ma_fast = price_data.rolling(window=fast_ma).mean()
    ma_slow = price_data.rolling(window=slow_ma).mean()

    # 2. 시뮬레이션 변수 초기화
    cash = initial_cash
    position_size = 0.0
    portfolio_value = initial_cash
    trades = []
    equity_curve = []

    # 3. 데이터 루프를 통한 시뮬레이션
    for i in range(1, len(price_data)):
        current_price = price_data.iloc[i]
        timestamp = price_data.index[i]
        
        # 포트폴리오 가치 업데이트
        portfolio_value = cash + (position_size * current_price)
        equity_curve.append({"timestamp": timestamp, "value": portfolio_value})

        # --- 거래 로직 ---
        # 골든 크로스: 매수 신호
        if ma_fast.iloc[i-1] < ma_slow.iloc[i-1] and ma_fast.iloc[i] > ma_slow.iloc[i]:
            if cash > 0: # 현금이 있을 때만 매수
                investment = cash # 전액 투자
                fee = investment * (fee_bps / 10000.0)
                position_size = (investment - fee) / current_price
                cash = 0
                trades.append({
                    "timestamp": timestamp, 
                    "type": "BUY", 
                    "price": current_price, 
                    "size": position_size
                })

        # 데드 크로스: 매도 신호
        elif ma_fast.iloc[i-1] > ma_slow.iloc[i-1] and ma_fast.iloc[i] < ma_slow.iloc[i]:
            if position_size > 0: # 포지션이 있을 때만 매도
                sale_value = position_size * current_price
                fee = sale_value * (fee_bps / 10000.0)
                cash = sale_value - fee
                position_size = 0
                trades.append({
                    "timestamp": timestamp, 
                    "type": "SELL", 
                    "price": current_price, 
                    "size": position_size # 매도 후 포지션은 0
                })

    # 4. 최종 결과 계산
    final_portfolio_value = cash + (position_size * price_data.iloc[-1])
    total_return_pct = ((final_portfolio_value / initial_cash) - 1) * 100
    
    return {
        "initial_cash": initial_cash,
        "final_portfolio_value": final_portfolio_value,
        "total_return_pct": total_return_pct,
        "number_of_trades": len(trades),
        "trades": trades,
        "equity_curve": equity_curve
    }

# ======================= 사용 예시 =======================
if __name__ == '__main__':
    # 테스트용 샘플 데이터 생성
    days = 365
    price = pd.Series(100 + pd.Series(range(days)) + pd.Series(pd.np.random.randn(days) * 5).cumsum(), 
                      index=pd.to_datetime(pd.date_range('2023-01-01', periods=days)))
    
    results = run_simple_backtest(price)
    
    print(f"초기 자본: ${results['initial_cash']:,.2f}")
    print(f"최종 자산: ${results['final_portfolio_value']:,.2f}")
    print(f"총 수익률: {results['total_return_pct']:.2f}%")
    print(f"총 거래 횟수: {results['number_of_trades']}")