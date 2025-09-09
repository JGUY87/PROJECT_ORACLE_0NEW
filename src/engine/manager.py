# -*- coding: utf-8 -*-
"""
메인 트레이딩 엔진 클래스
"""
import asyncio
import logging
import pandas as pd
from ..core.clients import get_exchange_client
from ..core.database import SessionLocal
from ..core.models import SignalLog
from .strategies import ma_crossover

class TradingEngine:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TradingEngine, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """초기화. 싱글턴 패턴으로 한번만 실행됩니다."""
        if not hasattr(self, 'initialized'):
            self.is_running = False
            self.current_strategy = None
            self.current_symbol = None
            self.last_strategy = None # 마지막 실행 전략 저장
            self.last_symbol = None # 마지막 실행 심볼 저장
            self.main_task = None
            self.client = get_exchange_client()
            self.initialized = True
            logging.info("TradingEngine initialized (Singleton)")

    def _log_signal_to_db(self, signal: str):
        """생성된 신호를 데이터베이스에 기록합니다."""
        db = SessionLocal()
        try:
            db_signal = SignalLog(
                symbol=self.current_symbol,
                strategy=self.current_strategy,
                signal=signal
            )
            db.add(db_signal)
            db.commit()
            logging.info(f"Signal '{signal}' for {self.current_symbol} logged to database.")
        except Exception as e:
            logging.error(f"Failed to log signal to database: {e}")
            db.rollback()
        finally:
            db.close()

    async def _run_loop(self):
        """메인 트레이딩 로직이 실행되는 비동기 루프"""
        logging.info(f"Engine loop started for {self.current_symbol} with strategy {self.current_strategy}")
        while self.is_running:
            try:
                # 1. 데이터 가져오기 (OHLCV)
                logging.info(f"Fetching OHLCV data for {self.current_symbol}...")
                ohlcv = await self.client.fetch_ohlcv(self.current_symbol, '1m', limit=100)
                if not ohlcv:
                    logging.warning("Could not fetch OHLCV data. Retrying in 60s.")
                    await asyncio.sleep(60)
                    continue

                # 2. 데이터프레임으로 변환
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.name = self.current_symbol # Set a name for logging inside the strategy

                # 3. 전략 적용하여 신호 생성
                if self.current_strategy == 'ma_crossover':
                    signal = ma_crossover.check_signal(df)
                else:
                    logging.warning(f"Strategy '{self.current_strategy}' is not supported. Holding.")
                    signal = 'hold'
                
                # 4. 데이터베이스에 신호 기록
                self._log_signal_to_db(signal)

                # 5. 신호에 따른 액션 (현재는 로깅만)
                if signal == 'buy':
                    logging.info(f"BUY signal detected for {self.current_symbol}. ACTION: Place buy order.")
                    # TODO: await order_helpers.place_market_order(self.current_symbol, 'buy', 0.01)
                elif signal == 'sell':
                    logging.info(f"SELL signal detected for {self.current_symbol}. ACTION: Place sell order.")
                    # TODO: await order_helpers.place_market_order(self.current_symbol, 'sell', 0.01)
                else: # 'hold'
                    logging.info(f"HOLD signal for {self.current_symbol}.")

                # 6. 루프 주기
                await asyncio.sleep(60)  # 1분 대기

            except asyncio.CancelledError:
                logging.info("Engine loop cancelled.")
                break
            except Exception as e:
                logging.error(f"An error occurred in the trading loop: {e}", exc_info=True)
                await asyncio.sleep(60) # 에러 발생 시에도 잠시 대기 후 계속

        logging.info("Engine loop has stopped.")
        self.is_running = False

    def start(self, strategy: str, symbol: str):
        """엔진을 시작합니다."""
        if self.is_running:
            return "Engine is already running."
        
        self.is_running = True
        self.current_strategy = strategy
        self.current_symbol = symbol
        self.last_strategy = strategy # 재시작을 위해 저장
        self.last_symbol = symbol # 재시작을 위해 저장
        self.main_task = asyncio.create_task(self._run_loop())
        logging.info(f"Engine task created for strategy '{strategy}' on '{symbol}'.")
        return f"Engine started with strategy '{strategy}' for symbol '{symbol}'."

    def stop(self):
        """엔진을 중지합니다."""
        if not self.is_running or not self.main_task:
            return "Engine is not running."
            
        self.is_running = False
        self.main_task.cancel()
        logging.info("Engine stop signal sent.")
        return "Engine stopping..."

    def get_status(self):
        """엔진의 현재 상태를 반환합니다."""
        return {
            "is_running": self.is_running,
            "strategy": self.current_strategy,
            "symbol": self.current_symbol
        }

    def restart(self):
        """엔진을 재시작합니다."""
        if not self.last_strategy or not self.last_symbol:
            return "No previous run to restart. Use /run first."
        
        if self.is_running:
            self.stop()
            # 비동기 환경에서 stop()이 완료될 시간을 잠시 줍니다.
            # 더 정교한 방법은 stop()이 완료되었다는 이벤트를 받는 것이지만, 우선 간단하게 구현합니다.
            async def _restart_task():
                await asyncio.sleep(3) # 3초 대기
                self.start(self.last_strategy, self.last_symbol)
            asyncio.create_task(_restart_task())
            return f"Restarting with strategy '{self.last_strategy}' for '{self.last_symbol}'..."
        else:
            self.start(self.last_strategy, self.last_symbol)
            return f"Starting with last known config: '{self.last_strategy}' for '{self.last_symbol}'."

    def switch_strategy(self, new_strategy: str):
        """실행 중인 전략을 변경합니다."""
        if not self.is_running:
            return "Engine is not running. Cannot switch strategy."
        
        logging.info(f"Switching strategy from '{self.current_strategy}' to '{new_strategy}'")
        self.current_strategy = new_strategy
        self.last_strategy = new_strategy # 재시작 시에도 적용되도록 업데이트
        return f"Strategy switched to '{new_strategy}'. It will be applied on the next cycle."

    def train_ppo_model(self, **kwargs):
        """
        PPO 모델 학습을 시작합니다.
        kwargs는 ppo_trainer.train_ppo_trading으로 전달됩니다.
        """
        logging.info("Initiating PPO model training...")
        result = ppo_trainer.train_ppo_trading(**kwargs)
        logging.info(f"PPO training initiated. Result: {result}")
        return result