#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
간소화된 실시간 트레이딩 엔진
CPU 사용량 및 메모리 최적화 버전
"""

import asyncio
import os
import sys
import gc
from typing import Optional, Dict, Any
from datetime import datetime
import pandas as pd
import numpy as np

# 프로젝트 루트 추가
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# 필수 모듈 임포트
from src.config.config_manager import load_config
from src.core import market_features
from src.core import strategy_recommender 
from src.core import model_loader
from src.engine.trade_executor_async import (
    get_session, get_realtime_symbols, fetch_top_symbols_data,
    get_last_price, get_balance, send_order, normalize_qty, send_telegram
)
from src.utils import report_utils
from src.utils.logger import get_logger

# 로거 및 설정
logger = get_logger(__name__)
config = load_config()

# 상수 설정
DRY_RUN = config.get('dry_run', True)
MIN_BALANCE = config.get('min_balance', 50.0)
ORDER_RISK_PCT = config.get('order_risk_pct', 0.15)
TOP_SYMBOLS_N = 2
SCAN_COUNT = 20

# 글로벌 상태
engine_running = True
trading_enabled = True

def now_kst_str():
    """현재 한국시간 문자열 반환"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log_trade_csv6(timestamp, strategy, symbol, price, qty, note):
    """거래 로그 기록 (6컬럼 형식)"""
    try:
        with open(f"{PROJECT_ROOT}/outputs/trade_log.csv", 'a', encoding='utf-8') as f:
            f.write(f"{timestamp},{strategy},{symbol},{price},{qty},{note}\n")
    except Exception as e:
        logger.error(f"거래 로그 기록 실패: {e}")

async def safe_sleep(seconds):
    """안전한 슬립"""
    try:
        await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        logger.info(f"Sleep interrupted after {seconds}s")
        raise

async def command_check_loop(session):
    """명령어 체크 루프"""
    global trading_enabled, engine_running
    
    while engine_running:
        try:
            # 기본 상태 체크만
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            break

async def main_trading_engine():
    """메인 트레이딩 엔진"""
    global engine_running
    
    logger.info("=== 간소화된 실시간 트레이딩 엔진 시작 ===")
    
    # 1. 세션 초기화
    try:
        session = await get_session()
        logger.info("✅ 거래소 세션 연결 성공")
    except Exception as e:
        logger.error(f"❌ 거래소 연결 실패: {e}")
        return
    
    # 2. AI 모델 로드
    try:
        model = model_loader.load_ppo_model()
        strategy_name = "default_ppo"
        logger.info("✅ AI 모델 로드 성공")
    except Exception as e:
        logger.warning(f"⚠️  AI 모델 로드 실패, 기본 전략 사용: {e}")
        model = None
        strategy_name = "ma_crossover"
    
    # 명령어 체크 태스크 시작
    command_task = asyncio.create_task(command_check_loop(session))
    
    try:
        while engine_running:
            try:
                if not trading_enabled:
                    report_utils.write_engine_status("PAUSED", "자동매매 일시중지 상태", now_kst_str())
                    await safe_sleep(5)
                    continue

                report_utils.write_engine_status("SCANNING", "거래 대상 스캔 중", now_kst_str())
                
                # 1. 심볼 목록 가져오기 (간소화)
                all_symbols = await get_realtime_symbols(session)
                market_data = await fetch_top_symbols_data(session, all_symbols, SCAN_COUNT, TOP_SYMBOLS_N)
                
                if not market_data:
                    logger.info("분석할 시장 데이터가 없습니다. 1분 후 재시도합니다.")
                    await safe_sleep(60)
                    continue

                # 2. 피처 추출 (최적화된 방식)
                valid_results = []
                longest_period = market_features.get_longest_indicator_period(strategy_name)
                
                # 최대 2개 심볼만 처리
                for symbol, market_info in list(market_data.items())[:2]:
                    if not market_info:
                        continue
                    
                    try:
                        # 간단한 타임프레임만 사용
                        timeframes = ['5m', '1h']
                        ohlcv_data = {}
                        
                        for tf in timeframes:
                            try:
                                limit = min(60, longest_period + 10)
                                bars = await session.fetch_ohlcv(symbol, tf, limit=limit)
                                
                                if bars and len(bars) > 0:
                                    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                                    ohlcv_data[tf] = df
                                
                                await asyncio.sleep(0.1)  # API 제한 방지
                                
                            except Exception as e:
                                logger.warning(f"[{symbol}] {tf} 데이터 가져오기 실패: {e}")
                                continue
                        
                        if not ohlcv_data:
                            continue
                            
                        # 피처 추출 (단순화)
                        feature_df_dict = {}
                        for tf, df in ohlcv_data.items():
                            if not df.empty and len(df) >= longest_period:
                                try:
                                    feature_df = market_features.extract_market_features(df.copy())
                                    if feature_df is not None and not feature_df.empty:
                                        feature_df_dict[tf] = feature_df
                                except Exception as e:
                                    logger.warning(f"[{symbol}] {tf} 피처 추출 실패: {e}")

                        if feature_df_dict:
                            df_merged = market_features.combine_mtf_features(feature_df_dict)
                            if df_merged is not None and not df_merged.empty:
                                valid_results.append({
                                    "symbol": symbol,
                                    "features": df_merged,
                                    "primary_df": feature_df_dict.get('5m')
                                })
                                
                    except Exception as e:
                        logger.warning(f"[{symbol}] 처리 중 오류: {e}")
                        continue

                if not valid_results:
                    report_utils.write_engine_status("WAITING", "유효 피처 없음", now_kst_str())
                    await safe_sleep(30)
                    continue

                # 3. AI 전략 추천
                recommended_strategy = strategy_recommender.ai_recommend_strategy_live(
                    valid_results, model, strategy_name, TOP_SYMBOLS_N
                )

                # 4. 거래 실행
                if not recommended_strategy or recommended_strategy.get('action') == 'hold':
                    report_utils.write_engine_status("WATCHING", "AI 추천 대기 중", now_kst_str())
                else:
                    symbol = recommended_strategy['symbol']
                    action = recommended_strategy['action']
                    confidence = recommended_strategy['confidence']
                    
                    # 신뢰도 필터 (60% 이상)
                    if confidence < 0.6:
                        logger.info(f"신뢰도 부족으로 거래 제외: {confidence:.3f}")
                    else:
                        current_price = await get_last_price(session, symbol)
                        report_utils.write_engine_status(
                            "EXECUTING", 
                            f"{symbol} {action} (신뢰도: {confidence:.2f})", 
                            now_kst_str()
                        )

                        if DRY_RUN:
                            logger.info(f"[DRY RUN] {symbol} {action} 신뢰도 {confidence:.3f} 모의 거래")
                        else:
                            # 실제 거래 로직 (간소화)
                            try:
                                balance = await get_balance(session, "USDT")
                                if balance < MIN_BALANCE:
                                    msg = f"잔고 부족 ({balance:.2f} USDT)"
                                    report_utils.write_engine_status("HALTED", msg, now_kst_str())
                                    await send_telegram(f"⚠️ {msg}")
                                    engine_running = False
                                    break
                                
                                side = 'buy' if action == 'long' else 'sell'
                                order_amount_usdt = balance * ORDER_RISK_PCT
                                order_qty_coin = order_amount_usdt / current_price
                                normalized_qty, _ = await normalize_qty(session, symbol, order_qty_coin)

                                if normalized_qty > 0:
                                    order_result = await send_order(session, symbol, side, normalized_qty)
                                    msg = (f"✅ [{symbol}] {action.upper()} 주문 실행\n"
                                           f" - 가격: ${order_result.get('price', current_price):.4f}\n"
                                           f" - 수량: {normalized_qty}\n"
                                           f" - 신뢰도: {confidence:.2f}")
                                    log_trade_csv6(now_kst_str(), f"AI_{action.upper()}", symbol, 
                                                  order_result.get('price', current_price), normalized_qty, 
                                                  f"Conf: {confidence:.2f}")
                                    await send_telegram(msg)
                                    
                            except Exception as e:
                                logger.exception(f"[{symbol}] 거래 실행 중 오류")
                                await send_telegram(f"🚨 [{symbol}] 거래 실행 실패: {e}")

                # 5. 메모리 정리 및 대기
                gc.collect()
                await safe_sleep(120)  # 2분 대기

            except asyncio.CancelledError:
                logger.info("메인 루프가 외부 요청에 의해 중단되었습니다.")
                break
            except Exception as e:
                logger.exception("메인 루프에서 처리되지 않은 예외 발생")
                report_utils.write_engine_status("ERROR", f"메인 루프 오류: {e}", now_kst_str())
                await safe_sleep(30)

    finally:
        # 정리 작업
        command_task.cancel()
        try:
            await command_task
        except asyncio.CancelledError:
            pass
        
        if session:
            await session.close()
        
        logger.info("🔚 트레이딩 엔진 종료")

if __name__ == "__main__":
    try:
        asyncio.run(main_trading_engine())
    except KeyboardInterrupt:
        logger.info("사용자 중단 요청으로 프로그램을 종료합니다.")
    except Exception as e:
        logger.exception(f"프로그램 실행 중 오류 발생: {e}")