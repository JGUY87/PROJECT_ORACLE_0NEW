# -*- coding: utf-8 -*-
"""
백테스트 실행을 위한 커맨드라인 인터페이스(CLI)
"""
import asyncio
import argparse
import logging
import os
from src.backtest.runner import run_ma_crossover_backtest
from src.notifier.telegram_notifier import send_backtest_results

# 기본 로깅 설정
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

async def main():
    parser = argparse.ArgumentParser(description="Run a moving average crossover backtest using vectorbt.")
    
    parser.add_argument(
        "--symbol", 
        type=str, 
        required=True, 
        help="Symbol to backtest (e.g., 'BTC/USDT')"
    )
    parser.add_argument(
        "--start_date", 
        type=str, 
        required=True, 
        help="Start date for backtest data (e.g., '2023-01-01')"
    )
    parser.add_argument(
        "--end_date", 
        type=str, 
        default=None, 
        help="End date for backtest data (e.g., '2024-01-01')"
    )
    parser.add_argument(
        "--fast_ma", 
        type=int, 
        default=10, 
        help="Fast moving average period"
    )
    parser.add_argument(
        "--slow_ma", 
        type=int, 
        default=30, 
        help="Slow moving average period"
    )
    parser.add_argument(
        "--no_telegram",
        action="store_true",
        help="Do not send a Telegram notification"
    )
    
    args = parser.parse_args()

    stats, stats_path, plot_path = await run_ma_crossover_backtest(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        fast_ma=args.fast_ma,
        slow_ma=args.slow_ma
    )
    if stats_path and plot_path:
        print(f"Backtest stats saved to: {stats_path}")
        print(f"Backtest plot saved to: {plot_path}")

        # 텔레그램 알림 보내기
        if not args.no_telegram:
            await send_backtest_results(str(stats_path), str(plot_path))

if __name__ == "__main__":
    # Poetry 환경에서 실행될 때 asyncio 이벤트 루프 관련 경고를 방지
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
