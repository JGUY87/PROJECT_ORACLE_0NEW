# -*- coding: utf-8 -*- 
# import gymnasium
# import sys
# sys.modules["gym"] = gymnasium

"""
MRL (Modular Reinforcement Learning) 기반 실시간 거래 엔진

- 실시간 심볼선정 → 피처추출 → 전략추천/AI → v5 주문/잔고 → 6컬럼 로그/리포트/텔레그램
- v5 고정: market/instruments-info, market/kline, account/wallet-balance, order/create
- 필수 파라미터: category='linear', accountType='UNIFIED'
- 로그 6컬럼: time,type,symbol,price,amount,info (KST)
- ErrCode 10001 방지: lotSizeFilter 기반 수량 보정
- ErrCode 10029 방지: SYMBOL_DENY_PATTERNS / SYMBOL_ALLOWLIST 기반 심볼 필터
"""
import os
import json
import re
import asyncio
import sys
import multiprocessing
from pathlib import Path
from datetime import datetime, timezone, timedelta
from decimal import Decimal, getcontext
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from loguru import logger
import pandas as pd
from dotenv import load_dotenv, find_dotenv
import ccxt.async_support as ccxt

PATCH_VERSION = "MRL-2025-09-14-v5-FINAL-PATCHED"

# ===== 경로/상수 =====
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS_FILE = PROJECT_ROOT / "configs/settings.json"
LOG_FILE = PROJECT_ROOT / "outputs/live_logs/trade_log.csv"
STATUS_FILE_PATH = PROJECT_ROOT / "outputs/engine_status.json"
KST = timezone(timedelta(hours=9))

# ===== 애플리케이션 상태 클래스 =====
@dataclass
class AppState:
    """애플리케이션 상태를 관리하는 데이터 클래스"""
    model: Optional[Any] = None  # PPO 모델 객체
    model_path: Optional[str] = None  # 현재 로드된 모델의 경로
    model_dir: str = str(PROJECT_ROOT / "outputs/models")  # 모델 검색 디렉토리
    last_model_check: float = 0.0  # 마지막 모델 체크 시간
    
    def __post_init__(self):
        """초기화 후 추가 설정"""
        # 모델 디렉토리가 존재하지 않으면 생성
        Path(self.model_dir).mkdir(parents=True, exist_ok=True)

# ===== 전역 변수 정의 =====
engine_running = True
trading_enabled = True

def process_initializer():
    """
    Each worker process will execute this function upon starting.
    This helps in pre-loading modules that might cause issues when loaded in a child process.
    """
    print(f"Initializing worker process: {os.getpid()}")
    import importlib.metadata

# Defer heavy imports
_report_utils = None
def get_report_utils():
    global _report_utils
    if _report_utils is None:
        from ..core import report_utils
        _report_utils = report_utils
    return _report_utils

_command_manager = None
def get_command_manager():
    global _command_manager
    if _command_manager is None:
        from src import command_manager
        _command_manager = command_manager
    return _command_manager

_telegram_sender = None
def get_telegram_sender():
    global _telegram_sender
    if _telegram_sender is None:
        from ..notifier.core.send_report_telegram import send_telegram_message
        _telegram_sender = send_telegram_message
    return _telegram_sender

_market_features = None
def get_market_features():
    global _market_features
    if _market_features is None:
        from ..core import market_features_optimized as market_features
        _market_features = market_features
    return _market_features

_strategy_recommender = None
def get_strategy_recommender():
    global _strategy_recommender
    if _strategy_recommender is None:
        from ..core import strategy_recommender
        _strategy_recommender = strategy_recommender
    return _strategy_recommender

_model_loader = None
def get_model_loader():
    global _model_loader
    if _model_loader is None:
        from ..core import model_loader
        _model_loader = model_loader
    return _model_loader

_smart_resource_manager = None
def get_smart_resource_manager():
    global _smart_resource_manager
    if _smart_resource_manager is None:
        from ..core.smart_resource_manager import get_resource_manager
        _smart_resource_manager = get_resource_manager()
    return _smart_resource_manager

_enhanced_trading_logic = None
def get_enhanced_trading_logic():
    global _enhanced_trading_logic
    if _enhanced_trading_logic is None:
        from ..core import enhanced_trading_logic
        _enhanced_trading_logic = enhanced_trading_logic
    return _enhanced_trading_logic

# ===== ENV 파라미터 =====
def _env_float(key: str, default: str) -> float:
    try:
        return float(os.getenv(key, default))
    except Exception:
        return float(default)

def _env_int(key: str, default: str) -> int:
    try:
        return int(os.getenv(key, default))
    except Exception:
        return int(default)

ORDER_RISK_PCT      = _env_float("ORDER_RISK_PCT", "0.10")
MIN_BALANCE         = _env_float("MIN_BALANCE", "10")
TOP_SYMBOLS_N       = _env_int("TOP_SYMBOLS_N", "3")
SCAN_COUNT          = _env_int("SCAN_COUNT", "30")
MAX_PARALLEL_FETCH  = _env_int("MAX_PARALLEL_FETCH", "6")
TF_PRIMARY          = os.getenv("TF_PRIMARY", "1")     # v5 interval 문자열 (기본 1분)
TIMEFRAMES          = [tf.strip() for tf in os.getenv("TIMEFRAMES", "1,5,60").split(',')]
FEATURE_MIN_BARS    = _env_int("FEATURE_MIN_BARS", "50")
DRY_RUN             = os.getenv("DRY_RUN", "false").lower() == "true"

# 기본 deny 패턴: 1000토큰/레버리지 토큰류 등
DEFAULT_DENY = r"^(1000|[A-Z]+BULLUSDT|[A-Z]+BEARUSDT)"
SYMBOL_DENY_PATTERNS = os.getenv("SYMBOL_DENY_PATTERNS", DEFAULT_DENY).strip()
SYMBOL_ALLOWLIST = os.getenv("SYMBOL_ALLOWLIST", "").strip()

# ===== 유틸 =====
def now_kst_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

async def safe_sleep(sec: float):
    try:
        await asyncio.sleep(sec)
    except asyncio.CancelledError:
        pass

# ===== Preflight Check =====
async def preflight_check(session: ccxt.bybit):
    """거래 실행 전 기본적인 연결 및 상태 확인"""
    try:
        # 간단한 잔고 조회로 API 연결 상태 확인
        await session.fetch_balance()
        return True
    except Exception as e:
        logger.error(f"Preflight check 실패: {e}")
        return False

# ===== CCXT 세션 =====
def get_session() -> ccxt.bybit:
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    use_testnet = os.getenv("BYBIT_USE_TESTNET", "false").lower() == "true"
    if not api_key or not api_secret:
        msg = "❌ BYBIT_API_KEY/BYBIT_API_SECRET 누락 (.env 확인)"
        get_report_utils().log_error(msg)
        raise RuntimeError(msg)
    
    exchange = ccxt.bybit({
        'apiKey': api_key,
        'secret': api_secret,
        'options': {
            'defaultType': 'swap',
        },
    })
    if use_testnet:
        exchange.set_sandbox_mode(True)
    return exchange

# ===== 6컬럼 통합 로그 =====
def log_trade_csv6(event_time: str, event_type: str, symbol: str, price: float, amount: float, info: str = "", log_path: Path = LOG_FILE) -> None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not log_path.exists()
        with open(log_path, "a", encoding="utf-8") as f:
            if write_header:
                f.write("time,type,symbol,price,amount,info\n")
            f.write(f"{event_time},{event_type},{symbol},{price},{amount},{info}\n")
    except Exception as e:
        get_report_utils().log_error(f"[통합로그 기록 실패] {e}")

# ===== 명령어 처리 로직 =====
async def handle_command(session: ccxt.bybit, command_data: dict):
    """수신된 명령어를 처리하고 결과를 반환합니다."""
    global engine_running, trading_enabled
    command = command_data.get("command")
    params = command_data.get("params", {})
    command_id = command_data.get("id")

    result = {"status": "error", "message": f"알 수 없는 명령어입니다: {command}"}
    
    # Lazy load model loader for strategy switching

    try:
        if command == "get_balance":
            balance = await get_balance(session)
            result = {"status": "success", "message": "잔고 조회가 완료되었습니다.", "data": {"USDT": f"{balance:.2f}"}}
        
        elif command == "get_summary":
            if STATUS_FILE_PATH.exists():
                with open(STATUS_FILE_PATH, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                result = {"status": "success", "message": "상태 요약 조회가 완료되었습니다.", "data": status_data}
            else:
                result = {"status": "error", "message": "상태 요약 파일을 찾을 수 없습니다."}

        elif command == "get_config":
            result = {"status": "success", "message": "현재 설정을 조회했습니다.", "data": _read_settings()}

        elif command == "stop_engine":
            engine_running = False
            result = {"status": "success", "message": "거래 엔진을 안전하게 중지합니다. 다음 루프에서 종료됩니다."}
        
        elif command == "restart_engine":
            engine_running = False
            Path("outputs/restart_signal.tmp").touch()
            result = {"status": "success", "message": "거래 엔진을 재시작합니다. 잠시 후 봇이 다시 시작됩니다."}

        # --- 신규 주문 처리 로직 ---
        elif command in ["order_buy", "order_sell"]:
            symbol = params.get("symbol")
            amount_usdt = params.get("amount")
            side = command.split('_')[1] # 'buy' or 'sell'

            if not symbol or not amount_usdt:
                result = {"status": "error", "message": "주문 파라미터(symbol, amount)가 누락되었습니다."}
            else:
                try:
                    # USDT를 실제 코인 수량로 변환
                    last_price = await get_last_price(session, symbol)
                    if last_price == 0:
                        raise ValueError("최신 가격을 가져올 수 없어 수량을 계산할 수 없습니다.")
                    
                    amount_coin = float(amount_usdt) / last_price
                    
                    # 수량 정규화
                    normalized_qty, market_info = await normalize_qty(session, symbol, amount_coin)
                    
                    if normalized_qty == 0:
                        min_qty = market_info.get('limits', {}).get('amount', {}).get('min', 'N/A')
                        raise ValueError(f"계산된 주문 수량이 너무 작습니다. (최소 주문 수량: {min_qty})")

                    # 주문 전송
                    order_result = await send_order(session, symbol, side, normalized_qty)
                    
                    log_trade_csv6(
                        now_kst_str(), f"REMOTE_{side.upper()}", symbol, 
                        order_result.get('price') or last_price, 
                        normalized_qty, f"Telegram Order by User"
                    )
                    result = {"status": "success", "message": f"{symbol}에 대한 {side} 주문이 성공적으로 전송되었습니다.", "data": order_result}

                except Exception as order_e:
                    error_msg = f"주문 처리 중 오류 발생: {order_e}"
                    logger.exception(error_msg)
                    result = {"status": "error", "message": error_msg}
        
        elif command == "engine_resume" or command == "engine_run":
            trading_enabled = True
            result = {"status": "success", "message": "자동매매를 시작/재개합니다."}

        elif command == "engine_pause":
            trading_enabled = False
            result = {"status": "success", "message": "자동매매를 일시중지합니다."}

        elif command == "order_close":
            symbol = params.get("symbol")
            if not symbol:
                result = {"status": "error", "message": "심볼이 지정되지 않았습니다."}
            else:
                try:
                    position = await get_open_position(session, symbol)
                    if not position or float(position.get('contracts', 0)) == 0:
                        result = {"status": "info", "message": f"{symbol}에 대한 오픈 포지션이 없습니다."}
                    else:
                        side = 'sell' if position['side'] == 'long' else 'buy'
                        amount = float(position['contracts'])
                        
                        # 포지션 종료 주문 전송
                        order_result = await send_order(session, symbol, side, amount)
                        
                        log_trade_csv6(
                            now_kst_str(), f"REMOTE_CLOSE", symbol, 
                            order_result.get('price') or position.get('entryPrice'), 
                            amount, f"Telegram Close Order by User"
                        )
                        result = {"status": "success", "message": f"{symbol} 포지션 종료 주문을 전송했습니다.", "data": order_result}
                except Exception as close_e:
                    error_msg = f"포지션 종료 중 오류 발생: {close_e}"
                    logger.exception(error_msg)
                    result = {"status": "error", "message": error_msg}

        elif command == "engine_switch_strategy":
            strategy_name = params.get("strategy_name")
            model_path = params.get("model_path")
            if not strategy_name or not model_path:
                result = {"status": "error", "message": "전략 이름과 모델 경로가 모두 필요합니다."}
            else:
                try:
                    new_settings = {
                        "strategy_name": strategy_name,
                        "model_path": model_path,
                        "strategy_timeframe": "1min" # 현재는 1min으로 고정
                    }
                    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                        json.dump(new_settings, f, indent=2)
                    
                    # 즉시 리로드는 메인 루프에서 자동으로 처리되므로 여기서는 설정만 저장
                    # load_and_update_model은 비동기 함수이므로 여기서 직접 호출하지 않음

                    result = {"status": "success", "message": f"전략이 {strategy_name}으로 변경되었습니다. 다음 사이클부터 적용됩니다."}
                except Exception as switch_e:
                    error_msg = f"전략 변경 중 오류 발생: {switch_e}"
                    logger.exception(error_msg)
                    result = {"status": "error", "message": error_msg}

        elif command in ["order_tp", "order_sl"]:
            symbol = params.get("symbol")
            trigger_price = params.get("trigger_price")
            amount_usdt = params.get("amount")
            order_type = command.split('_')[1] # 'tp' or 'sl'

            if not all([symbol, trigger_price, amount_usdt]):
                result = {"status": "error", "message": "TP/SL 주문에 필요한 파라미터(symbol, trigger_price, amount)가 누락되었습니다."}
            else:
                try:
                    position = await get_open_position(session, symbol)
                    if not position or float(position.get('contracts', 0)) == 0:
                        result = {"status": "info", "message": f"{symbol}에 대한 오픈 포지션이 없어 TP/SL을 설정할 수 없습니다."}
                    else:
                        # 포지션 방향에 따라 TP/SL 주문 방향 결정
                        # 롱 포지션: TP는 매도, SL은 매도
                        # 숏 포지션: TP는 매수, SL은 매수
                        side = 'sell' if position['side'] == 'long' else 'buy'

                        # USDT 수량을 코인 수량으로 변환
                        last_price = await get_last_price(session, symbol)
                        amount_coin = float(amount_usdt) / last_price
                        normalized_qty, _ = await normalize_qty(session, symbol, amount_coin)

                        if normalized_qty > 0:
                            # CCXT는 TP/SL을 params의 일부로 처리하는 경우가 많음
                            # create_order를 사용하여 조건부 주문을 생성해야 할 수 있음
                            # 여기서는 간단하게 stop-loss/take-profit order를 생성 시도
                            order_params = {
                                'reduceOnly': True,
                            }
                            if order_type == 'tp':
                                order_params['takeProfitPrice'] = float(trigger_price)
                            else: # sl
                                order_params['stopLossPrice'] = float(trigger_price)

                            # create_order를 사용하여 조건부 시장가 주문 생성
                            order_result = await session.create_order(
                                symbol=symbol,
                                type='market', # 트리거 시 시장가로 체결
                                side=side,
                                amount=normalized_qty,
                                params=order_params
                            )
                            
                            log_trade_csv6(
                                now_kst_str(), f"REMOTE_{order_type.upper()}", symbol, 
                                float(trigger_price), normalized_qty, 
                                f"Telegram {order_type.upper()} Order by User"
                            )
                            result = {"status": "success", "message": f"{symbol}에 대한 {order_type.upper()} 주문이 성공적으로 설정되었습니다.", "data": order_result}
                        else:
                            result = {"status": "error", "message": "계산된 주문 수량이 0보다 작아 주문을 보낼 수 없습니다."}

                except Exception as tpsl_e:
                    error_msg = f"TP/SL 주문 처리 중 오류 발생: {tpsl_e}"
                    logger.exception(error_msg)
                    result = {"status": "error", "message": error_msg}

    except Exception as e:
        error_msg = f"명령어 '{command}' 처리 중 오류 발생: {e}"
        logger.exception(error_msg)
        result = {"status": "error", "message": error_msg}

    if command_id:
        cm = get_command_manager()
        cm.write_result(command_id, result)

async def command_check_loop(session: ccxt.bybit):
    """명령어 처리 루프"""
    global engine_running, trading_enabled  # 전역 변수 선언 추가
    logger.info("명령어 처리 루프 시작.")
    cm = get_command_manager()
    while engine_running:
        command_data = cm.get_command()
        if command_data:
            await handle_command(session, command_data)
        await asyncio.sleep(1)
    logger.info("명령어 처리 루프 종료.")


# ===== 포지션 조회 =====
async def get_open_position(session: ccxt.bybit, symbol: str) -> Dict[str, Any] | None:
    """지정된 심볼의 현재 오픈 포지션을 조회합니다."""
    try:
        params = {'category': 'linear', 'symbol': symbol}
        positions = await session.fetch_positions(symbols=[symbol], params=params)
        
        # fetch_positions는 리스트를 반환하며, 필터링된 결과는 보통 하나의 요소만 가짐
        for position in positions:
            # v5 API 응답에서 'contracts' 또는 'size' 필드는 포지션 수량을 나타냄
            # ccxt 통합 라이브러리는 이를 'contracts'로 표준화하는 경향이 있음
            if position.get('contracts') and float(position['contracts']) > 0:
                return position
    except Exception as e:
        logger.exception(f"[{symbol}] 포지션 조회 중 오류 발생: {e}")
    return None


# ===== 심볼 조회 (+ 필터링) =====
async def get_realtime_symbols(session: ccxt.bybit) -> List[str]:
    try:
        # Bybit v5 API는 markets를 미리 로드할 필요가 없으며, 직접 엔드포인트를 호출합니다.
        # category='linear'는 USDT 무기한/선형 계약을 의미합니다.
        params = {'category': 'linear'}
        markets = await session.fetch_markets(params)
        
        syms = [
            s['symbol'] for s in markets
            if s.get('active')
        ]
        
        if not syms:
            logger.warning("필터링 후 거래 가능한 USDT 선물 심볼이 없습니다.")

        if SYMBOL_DENY_PATTERNS:
            rx = re.compile(SYMBOL_DENY_PATTERNS)
            syms = [s for s in syms if not rx.search(s)]
        if SYMBOL_ALLOWLIST:
            allow_set = {x.strip() for x in SYMBOL_ALLOWLIST.split(",") if x.strip()}
            syms = [s for s in syms if s in allow_set]
        return syms
    except Exception as e:
        logger.exception(f"[심볼 조회 실패] {e}")
        return []

# ===== 캔들 파서/조회 (CCXT) =====
def _parse_kline_to_df(raw_ohlcv: list) -> pd.DataFrame:
    if not raw_ohlcv:
        return pd.DataFrame()
    
    df = pd.DataFrame(raw_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert(KST)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna()
    return df.sort_values("timestamp")

async def fetch_candles(session: ccxt.bybit, symbol: str, interval: str = TF_PRIMARY, longest_period: int = 200) -> pd.DataFrame:
    from ..config.data_windows import required_min_bars
    timeframe_mapping = {
        "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
        "60": "1h", "120": "2h", "240": "4h", "360": "6h", "720": "12h",
        "D": "1d", "W": "1w", "M": "1M"
    }
    ccxt_interval = timeframe_mapping.get(str(interval), interval)
    limit = required_min_bars(longest_period, ccxt_interval)

    try:
        ohlcv = await session.fetch_ohlcv(symbol, timeframe=ccxt_interval, limit=limit)
        return _parse_kline_to_df(ohlcv)
    except Exception as e:
        logger.exception(f"[{symbol}] 캔들 조회 실패: {e}")
        return pd.DataFrame()

# ===== 최신가 조회 (CCXT) =====
async def get_last_price(session: ccxt.bybit, symbol: str) -> float:
    try:
        ticker = await session.fetch_ticker(symbol)
        if ticker and 'last' in ticker:
            return float(ticker['last'])
    except Exception:
        pass
    df = await fetch_candles(session, symbol, interval=TF_PRIMARY, longest_period=1)
    if not df.empty:
        return float(df["close"].iloc[0])
    return 0.0

# ===== 상위 심볼 데이터 페치 =====
async def fetch_top_symbols_data(session: ccxt.bybit, symbols: List[str], scan_count: int, top_n: int) -> Dict[str, Any]:
    """
    상위 N개 심볼에 대한 시장 데이터를 가져옵니다.
    (수정: 심볼 유효성 검사 추가)
    """
    try:
        await session.load_markets(True)
        
        market_data = {}
        
        # 로드된 마켓에 대해 심볼 필터링
        valid_symbols = [s for s in symbols if s in session.markets]
        symbols_to_scan = valid_symbols[:scan_count] if len(valid_symbols) > scan_count else valid_symbols
        
        for symbol in symbols_to_scan:
            try:
                # 24시간 통계 가져오기
                ticker = await session.fetch_ticker(symbol)
                if ticker:
                    volume_usd = float(ticker.get('quoteVolume', 0))
                    price_change_pct = float(ticker.get('percentage', 0))
                    
                    market_data[symbol] = {
                        'volume_usd': volume_usd,
                        'price_change_pct': price_change_pct,
                        'last_price': float(ticker.get('last', 0)),
                        'ticker': ticker
                    }
                    
            except Exception as e:
                logger.warning(f"[{symbol}] 티커 데이터 가져오기 실패: {e}")
                continue
        
        # 거래량 기준으로 상위 N개 선택
        if market_data:
            sorted_symbols = sorted(
                market_data.items(),
                key=lambda x: x[1]['volume_usd'],
                reverse=True
            )[:top_n]
            
            # 상위 심볼들만 반환
            top_market_data = dict(sorted_symbols)
            logger.info(f"상위 {len(top_market_data)}개 심볼 선정: {list(top_market_data.keys())}")
            return top_market_data
        
        return {}
        
    except Exception as e:
        logger.exception(f"상위 심볼 데이터 페치 실패: {e}")
        return {}

# ===== 잔고 조회 (CCXT) =====
async def get_balance(session: ccxt.bybit, coin: str = "USDT") -> float:
    try:
        balance = await session.fetch_balance()
        # v5 API 응답 구조에 맞게 수정
        if balance.get('total') and coin in balance['total']:
            return float(balance['total'][coin])
        # fallback
        if coin in balance['free']:
            return float(balance['free'][coin])
        return 0.0
    except Exception as e:
        logger.exception(f"[{coin}] 잔고 조회 실패: {e}")
        return 0.0

# ===== 수량 정규화 & 주문 (CCXT) =====
getcontext().prec = 20

async def normalize_qty(session: ccxt.bybit, symbol: str, raw_qty: float) -> Tuple[float, Dict[str, Any]]:
    await session.load_markets(True) 
    market = session.markets[symbol]
    
    limits = market.get('limits', {})
    amount_limits = limits.get('amount', {})
    min_qty = amount_limits.get('min')
    max_qty = amount_limits.get('max')

    qty = Decimal(str(raw_qty))
    
    precision = market.get('precision', {}).get('amount')
    if precision is not None:
        step = Decimal('1e-' + str(int(precision)))
        qty = (qty // step) * step

    if min_qty is not None and qty < Decimal(str(min_qty)):
        return 0.0, market
    
    if max_qty is not None and qty > Decimal(str(max_qty)):
        qty = Decimal(str(max_qty))

    return float(qty), market

async def send_order(session: ccxt.bybit, symbol: str, side: str, amount: float, params: dict = None) -> Dict[str, Any]:
    if DRY_RUN:
        return {'id': 'DRYRUN', 'amount': amount, 'price': None, 'info': {}}
    try:
        order = await session.create_market_order(symbol, side.lower(), amount, params=params)
        return order
    except Exception as e:
        raise RuntimeError(f"[주문 실패] {symbol}/{side}/{amount} → {e}")

# ===== 설정/모델 자동감지 =====
_last_cfg = {"strategy_name": None, "model_path": None, "strategy_timeframe": None, "mtime": 0}
_model_cache: Dict[str, Any] = {}

def _read_settings() -> Dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return {"strategy_name":"ppo","model_path":"outputs/ppo_model.zip","strategy_timeframe":"1min"}
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        return json.load(f)

async def load_and_update_model(
    app_state: AppState,
    executor: Optional[ProcessPoolExecutor] = None
) -> None:
    """
    AI 모델을 비동기적으로 로드하거나 업데이트합니다.
    - ProcessPoolExecutor를 사용하여 CPU 바운드 작업을 별도의 프로세스에서 실행합니다.
    - 최신 모델을 찾지 못하면 백업 모델 로드를 시도합니다.
    """
    loop = asyncio.get_running_loop()
    model_loader = get_model_loader()

    try:
        logger.info("최신 AI 모델 경로를 찾는 중...")
        model_path = await loop.run_in_executor(
            executor, model_loader.get_latest_model_path, app_state.model_dir
        )

        # 모델 경로가 변경되었거나, 현재 모델이 없는 경우에만 모델을 다시 로드합니다.
        if model_path and (app_state.model is None or Path(model_path) != Path(app_state.model_path)):
            logger.info(f"새로운/업데이트된 모델 발견: {model_path}. 모델을 로드합니다.")
            
            model = await loop.run_in_executor(
                executor, model_loader.load_ppo_model, model_path
            )
            
            if model:
                app_state.model = model
                app_state.model_path = model_path
                logger.success("AI 모델이 성공적으로 업데이트되었습니다.")
            else:
                logger.error("새 모델 로드에 실패했습니다. 이전 모델(있다면)을 계속 사용합니다.")

        # 모델 경로를 찾지 못했고, 현재 로드된 모델도 없는 경우 (초기 시작 시)
        elif not model_path and app_state.model is None:
            logger.warning("기본 경로에서 모델을 찾을 수 없습니다. 백업 모델 로드를 시도합니다.")
            
            # load_ppo_model은 경로가 None이거나 유효하지 않을 때 백업을 시도합니다.
            model = await loop.run_in_executor(
                executor, model_loader.load_ppo_model, None
            )
            
            if model:
                app_state.model = model
                # 백업 모델 경로를 상태에 저장할 수 있습니다.
                app_state.model_path = str(model_loader.BACKUP_MODEL_PATH)
                logger.success("백업 AI 모델이 성공적으로 로드되었습니다.")
            else:
                logger.error("기본 및 백업 모델 로드에 모두 실패했습니다. AI 추천을 사용할 수 없습니다.")
        
        else:
            logger.info("현재 AI 모델이 최신 버전이거나, 변경 사항이 없습니다.")

    except Exception as e:
        logger.error(f"모델 로딩 또는 업데이트 중 예상치 못한 오류 발생: {e}", exc_info=True)


async def main_loop(app_state: AppState, executor: ProcessPoolExecutor, session: ccxt.bybit):
    """메인 거래 로직 루프 (최적화된 버전)"""
    global engine_running, trading_enabled

    # 스마트 리소스 매니저 시작
    resource_manager = get_smart_resource_manager()
    await resource_manager.start()

    # Get necessary modules via deferred loaders
    report_utils = get_report_utils()
    market_features = get_market_features()
    strategy_recommender = get_strategy_recommender()
    enhanced_trading_logic = get_enhanced_trading_logic()
    send_telegram = get_telegram_sender()
    
    logger.info("===== 실시간 거래 엔진 시작 =====")
    logger.info(f"VERSION: {PATCH_VERSION}")
    logger.info(f"DRY_RUN: {DRY_RUN}")

    if app_state.model is None:
        report_utils.write_engine_status("ERROR", "모델 로드 실패", now_kst_str())
        await send_telegram("🚨 AI 모델을 로드할 수 없어 엔진을 시작할 수 없습니다. 확인이 필요합니다.")
        return
    
    symbol_selector = enhanced_trading_logic.get_smart_symbol_selector()
    ai_filter = enhanced_trading_logic.get_enhanced_ai_filter()
    
    settings = _read_settings()
    strategy_name = settings.get("strategy_name", "ppo")
    model = app_state.model

    command_task = asyncio.create_task(command_check_loop(session))

    try:
        while engine_running:
            top_symbols_list = [] # Initialize for the loop
            if not trading_enabled:
                report_utils.write_engine_status("PAUSED", "자동매매 일시중지 상태", now_kst_str(), top_symbols=top_symbols_list)
                await safe_sleep(5)
                continue

            report_utils.write_engine_status("SCANNING", "거래 대상 스캔 중", now_kst_str(), top_symbols=top_symbols_list)
            
            all_symbols = await get_realtime_symbols(session)
            
            market_data = await fetch_top_symbols_data(session, all_symbols, SCAN_COUNT, TOP_SYMBOLS_N)
            
            if not market_data:
                logger.info("분석할 시장 데이터가 없습니다. 1분 후 재시도합니다.")
                report_utils.write_engine_status("WAITING", "시장 데이터 없음", now_kst_str(), top_symbols=top_symbols_list)
                await safe_sleep(60)
                continue

            market_condition = symbol_selector.detect_market_condition(market_data)
            logger.info(f"감지된 시장 상황: {market_condition}")
            
            top_symbols_smart = symbol_selector.select_top_symbols(
                market_data, top_n=TOP_SYMBOLS_N, market_condition=market_condition
            )
            
            top_symbols_list = list(top_symbols_smart.keys()) if top_symbols_smart else []

            if not top_symbols_smart:
                logger.info("스마트 선정 결과 거래 가능한 심볼이 없습니다.")
                report_utils.write_engine_status("WAITING", "스마트 선정 심볼 없음", now_kst_str(), top_symbols=top_symbols_list)
                await safe_sleep(60)
                continue

            valid_results = []
            longest_period = market_features.get_longest_indicator_period(strategy_name)
            
            symbols_batch = list(top_symbols_smart.items())
            
            import psutil
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024
            
            for symbol, market_info in symbols_batch:
                if not market_info:
                    continue
                
                current_memory = process.memory_info().rss / 1024 / 1024
                if current_memory - initial_memory > 500:
                    logger.warning(f"메모리 사용량이 {current_memory:.1f}MB로 증가하여 처리를 중단합니다.")
                    break
                
                try:
                    timeframes = ['5m', '1h', '1d']
                    ohlcv_data = {}
                    
                    for tf in timeframes:
                        try:
                            limit = min(100, longest_period + 20)
                            bars = await session.fetch_ohlcv(symbol, tf, limit=limit)
                            
                            if bars and len(bars) > 0:
                                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                                ohlcv_data[tf] = df
                            
                            await asyncio.sleep(0.1)
                            
                        except Exception as e:
                            logger.warning(f"[{symbol}] {tf} OHLCV 데이터 가져오기 실패: {e}")
                            continue
                    
                    if not ohlcv_data:
                        logger.warning(f"[{symbol}] 사용 가능한 OHLCV 데이터가 없습니다.")
                        continue
                        
                except Exception as e:
                    logger.exception(f"[{symbol}] OHLCV 데이터 처리 중 오류: {e}")
                    continue
                
                feature_df_dict = {}
                loop = asyncio.get_running_loop()
                
                for tf, df in ohlcv_data.items():
                    if not df.empty and len(df) >= longest_period:
                        try:
                            feature_df = await loop.run_in_executor(
                                executor, market_features.extract_market_features, df.copy()
                            )
                            if feature_df is not None and not feature_df.empty:
                                feature_df_dict[tf] = feature_df
                            
                            await asyncio.sleep(0.2)
                            
                        except Exception as e:
                            logger.warning(f"[{symbol}] {tf} 피처 추출 실패: {e}")
                            continue

                if not feature_df_dict:
                    continue

                try:
                    df_merged = market_features.combine_mtf_features(feature_df_dict)
                    
                    if df_merged is not None and not df_merged.empty:
                        valid_results.append({
                            "symbol": symbol,
                            "features": df_merged,
                            "primary_df": feature_df_dict.get(TF_PRIMARY)
                        })
                        
                        await asyncio.sleep(0.5)
                        
                except Exception as e:
                    logger.warning(f"[{symbol}] MTF 피처 병합 실패: {e}")
                    continue

            if not valid_results:
                report_utils.write_engine_status("WAITING", "유효 피처 없음", now_kst_str(), top_symbols=top_symbols_list)
                await safe_sleep(10)
                continue

            recommended_strategy = strategy_recommender.ai_recommend_strategy_live(valid_results, model, strategy_name, TOP_SYMBOLS_N)

            if not recommended_strategy or recommended_strategy.get('action') == 'hold':
                report_utils.write_engine_status("WATCHING", "AI 추천 대기 중", now_kst_str(), top_symbols=top_symbols_list)
            else:
                symbol = recommended_strategy['symbol']
                action = recommended_strategy['action']
                confidence = recommended_strategy['confidence']
                
                current_price = await get_last_price(session, symbol)
                
                report_utils.write_engine_status("EXECUTING", f"{symbol} {action} (신뢰도: {confidence:.2f})", now_kst_str(), top_symbols=top_symbols_list)

                try:
                    balance = await get_balance(session, "USDT")
                    if balance < MIN_BALANCE:
                        msg = f"잔고 부족 ({balance:.2f} USDT)으로 거래를 중단합니다."
                        report_utils.write_engine_status("HALTED", msg, now_kst_str(), top_symbols=top_symbols_list)
                        await send_telegram(f"⚠️ {msg}")
                        engine_running = False
                        break
                    
                    side = 'buy' if action == 'long' else 'sell'
                    order_amount_usdt = balance * ORDER_RISK_PCT
                    
                    if current_price == 0:
                        raise ValueError("최신 가격을 가져올 수 없어 주문 수량 계산 불가")
                    
                    order_qty_coin = order_amount_usdt / current_price
                    normalized_qty, _ = await normalize_qty(session, symbol, order_qty_coin)

                    if normalized_qty > 0 and not DRY_RUN:
                        order_result = await send_order(session, symbol, side, normalized_qty)
                        msg = (
                               f"✅ [{symbol}] {action.upper()} 주문 실행\n"
                               f" - 가격: ${order_result.get('price', current_price):.4f}\n"
                               f" - 수량: {normalized_qty}\n"
                               f" - 신뢰도: {confidence:.2f}"
                               )
                        log_trade_csv6(now_kst_str(), f"AI_{action.upper()}", symbol, order_result.get('price', current_price), normalized_qty, f"Conf: {confidence:.2f}")
                        await send_telegram(msg)
                    elif DRY_RUN:
                        logger.info(f"[DRY RUN] {symbol} {side} {normalized_qty} 주문 시뮬레이션")
                    else:
                        logger.warning(f"[{symbol}] 계산된 주문 수량이 0 이하이므로 주문을 보내지 않습니다.")

                except Exception as e:
                    logger.exception(f"[{symbol}] 거래 실행 중 오류 발생")
                    await send_telegram(f"🚨 [{symbol}] 거래 실행 실패: {e}")

            metrics = resource_manager.get_metrics()
            current_load = metrics.get('cpu_percent', 0)
            if current_load > 80:
                sleep_time = 180
            elif current_load > 60:
                sleep_time = 120
            else:
                sleep_time = 90
                
            await safe_sleep(sleep_time)

    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("메인 루프가 외부 요청에 의해 중단되었습니다.")
    except Exception as e:
        logger.exception("메인 루프에서 처리되지 않은 예외 발생")
        report_utils.write_engine_status("ERROR", f"메인 루프 오류: {e}", now_kst_str())
        await send_telegram(f"🔥 엔진 메인 루프 오류: {e}")
        await safe_sleep(30)

    finally:
        await resource_manager.stop()
        
    command_task.cancel()
    try:
        await command_task
    except asyncio.CancelledError:
        pass
    logger.info("메인 거래 루프 종료.")


def main():
    """
    Real-time trading engine entry point.
    CPU 과부하 방지를 위해 제한된 워커 사용.
    """
    load_dotenv()
    
    max_workers = min(2, os.cpu_count() // 2)
    logger.info(f"ProcessPoolExecutor 워커 수: {max_workers}/{os.cpu_count()}")
    
    mp_context = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(
        max_workers=max_workers,
        mp_context=mp_context,
        initializer=process_initializer
    ) as executor:
        
        async def run():
            session = None
            try:
                session = get_session()
                
                try:
                    preflight_ok = await asyncio.wait_for(preflight_check(session), timeout=30.0)
                    if not preflight_ok:
                        logger.error("Preflight check 실패로 엔진을 시작할 수 없습니다.")
                        return
                except asyncio.TimeoutError:
                    logger.error("Preflight check 타임아웃 (30초)")
                    return
                
                app_state = AppState()
                
                try:
                    await asyncio.wait_for(load_and_update_model(app_state, executor), timeout=60.0)
                except asyncio.TimeoutError:
                    logger.error("모델 로드 타임아웃 (60초)")
                    return
                
                await main_loop(app_state, executor, session)

            except (KeyboardInterrupt, asyncio.CancelledError):
                logger.info("사용자에 의해 엔진이 중지되었습니다.")
            except Exception as e:
                try:
                    report_utils = get_report_utils()
                    report_utils.log_error(f"엔진 실행 중 치명적 오류 발생: {e}")
                except Exception as log_e:
                    logger.critical(f"로깅 시스템 초기화 실패: {log_e}")
                    logger.critical(f"원본 오류: {e}")
            finally:
                if session:
                    try:
                        await asyncio.wait_for(session.close(), timeout=10.0)
                    except asyncio.TimeoutError:
                        logger.warning("세션 종료 타임아웃")
                    except Exception as close_e:
                        logger.warning(f"세션 종료 중 오류: {close_e}")
                logger.info("거래 엔진 리소스를 정리했습니다.")

        try:
            asyncio.run(run())
        except KeyboardInterrupt:
            # This will catch the interrupt if it happens during asyncio.run() setup
            logger.info("엔진 시작 중 중단되었습니다.")


if __name__ == '__main__':
    if sys.gettrace() is None:
        multiprocessing.freeze_support()
    main()
