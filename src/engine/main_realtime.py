# -*- coding: utf-8 -*-
"""
🧠 LIBRA 실전 자동매매 실시간 루프
(오라클 2025 / pybit 2.3.0 + REST v5 통합판, 수량 규격 자동보정/프리플라이트/심볼 필터 포함)

- 실시간 심볼선정 → 피처추출 → 전략추천/AI → v5 주문/잔고 → 6컬럼 로그/리포트/텔레그램
- v5 고정: market/instruments-info, market/kline, account/wallet-balance, order/create
- 필수 파라미터: category='linear', accountType='UNIFIED'
- 로그 6컬럼: time,type,symbol,price,amount,info (KST)
- ErrCode 10001 방지: lotSizeFilter 기반 수량 보정
- ErrCode 10029 방지: SYMBOL_DENY_PATTERNS / SYMBOL_ALLOWLIST 기반 심볼 필터
"""
PATCH_VERSION = "MRL-2025-08-13-v3"


import os
from loguru import logger
import json
import re
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal, getcontext
from typing import Dict, Any, List, Tuple

import pandas as pd
from dotenv import load_dotenv, find_dotenv

# ⭐ CCXT (통합 거래소 라이브러리)
import ccxt.async_support as ccxt

# ===== 내부 모듈 =====
from ..core.model_loader import load_model
from ..core.strategy_recommender import ai_recommend_strategy_live
from ..core.market_features import extract_multi_timeframe_features
from ..core.report_utils import log_error, write_engine_status, generate_daily_report
from ..notifier.core.send_report_telegram import send_telegram_message as send_telegram

# ===== 경로/상수 =====
SETTINGS_FILE = os.path.join("config", "settings.json")
LOG_FILE = os.path.join("outputs", "live_logs", "trade_log.csv")
KST = timezone(timedelta(hours=9))

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

# ===== CCXT 세션 =====
def get_session() -> ccxt.bybit:
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    use_testnet = os.getenv("BYBIT_USE_TESTNET", "false").lower() == "true"
    if not api_key or not api_secret:
        msg = "❌ BYBIT_API_KEY/BYBIT_API_SECRET 누락 (.env 확인)"
        log_error(msg); raise RuntimeError(msg)
    
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
def log_trade_csv6(event_time: str, event_type: str, symbol: str, price: float, amount: float, info: str = "", log_path: str = LOG_FILE) -> None:
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        write_header = not os.path.exists(log_path)
        with open(log_path, "a", encoding="utf-8") as f:
            if write_header:
                f.write("time,type,symbol,price,amount,info\n")
            f.write(f"{event_time},{event_type},{symbol},{price},{amount},{info}\n")
    except Exception as e:
        log_error(f"[통합로그 기록 실패] {e}")



# ===== 심볼 조회 (+ 필터링) =====
async def get_realtime_symbols(session: ccxt.bybit) -> List[str]:
    try:
        await session.load_markets(True)
        markets = session.markets
        
        # --- FINAL DEBUGGING ---
        swap_markets = [s for s in markets.values() if s.get('type') == 'swap']
        logger.debug(f"찾은 SWAP 마켓 수: {len(swap_markets)}")
        if swap_markets:
            # SWAP 마켓들의 quote, active 상태를 로깅
            for i, market in enumerate(swap_markets[:5]): # 샘플 5개만
                logger.debug(f"SWAP 마켓 샘플 {i+1}: symbol={market.get('symbol')}, active={market.get('active')}, quote={market.get('quote')}")
        # --- END DEBUGGING ---

        syms = [
            s['symbol'] for s in swap_markets
            if s.get('active') and s.get('quote') == 'USDT'
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
        log_error(f"[심볼 조회 실패] {e}")
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

async def fetch_candles(session: ccxt.bybit, symbol: str, interval: str = TF_PRIMARY, limit: int = 200) -> pd.DataFrame:
    # CCXT timeframes: '1m', '5m', '1h', '1d'. Bybit's '1', '60', 'D' 등과 매핑.
    timeframe_mapping = {
        "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
        "60": "1h", "120": "2h", "240": "4h", "360": "6h", "720": "12h",
        "D": "1d", "W": "1w", "M": "1M"
    }
    ccxt_interval = timeframe_mapping.get(str(interval), interval)

    try:
        ohlcv = await session.fetch_ohlcv(symbol, timeframe=ccxt_interval, limit=limit)
        return _parse_kline_to_df(ohlcv)
    except Exception as e:
        log_error(f"[{symbol}] 캔들 조회 실패: {e}")
        return pd.DataFrame()

# ===== 최신가 조회 (CCXT) =====
async def get_last_price(session: ccxt.bybit, symbol: str) -> float:
    try:
        ticker = await session.fetch_ticker(symbol)
        if ticker and 'last' in ticker:
            return float(ticker['last'])
    except Exception:
        pass
    # fallback: 최근 캔들 종가
    df = await fetch_candles(session, symbol, interval=TF_PRIMARY, limit=1)
    if not df.empty:
        return float(df["close"].iloc[0])
    return 0.0

# ===== 잔고 조회 (CCXT) =====
async def get_balance(session: ccxt.bybit, coin: str = "USDT") -> float:
    try:
        balance = await session.fetch_balance()
        if coin in balance['free']:
            return float(balance['free'][coin])
        return 0.0
    except Exception as e:
        log_error(f"[{coin}] 잔고 조회 실패: {e}")
        return 0.0

# ===== 수량 정규화 & 주문 (CCXT) =====
getcontext().prec = 20 # for Decimal

async def normalize_qty(session: ccxt.bybit, symbol: str, raw_qty: float) -> Tuple[float, Dict[str, Any]]:
    """CCXT market data를 기반으로 수량을 최소/스텝에 맞게 보정"""
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

async def send_order(session: ccxt.bybit, symbol: str, side: str, amount: float) -> Dict[str, Any]:
    if DRY_RUN:
        return {'id': 'DRYRUN', 'amount': amount, 'price': None, 'info': {}}
    try:
        order = await session.create_market_order(symbol, side.lower(), amount)
        return order
    except Exception as e:
        raise RuntimeError(f"[주문 실패] {symbol}/{side}/{amount} → {e}")

# ===== 설정/모델 자동감지 =====
_last_cfg = {"strategy_name": None, "model_path": None, "strategy_timeframe": None, "mtime": 0}
_model_cache: Dict[str, Any] = {}

def _read_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_FILE):
        return {"strategy_name":"ppo","model_path":"outputs/ppo_model.zip","strategy_timeframe":"1min"}
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        return json.load(f)

def _need_reload(cfg: Dict[str, Any]) -> bool:
    sname = cfg.get("strategy_name","ppo")
    mpath = cfg.get("model_path","outputs/ppo_model.zip")
    tf = cfg.get("strategy_timeframe","1min")
    mtime = os.path.getmtime(mpath) if os.path.exists(mpath) else 0
    prev = _last_cfg
    return (sname!=prev.get("strategy_name") or mpath!=prev.get("model_path") or
            tf!=prev.get("strategy_timeframe") or mtime>prev.get("mtime",0))

def load_and_update_model() -> Dict[str, Any]:
    try:
        cfg = _read_settings()
        if _need_reload(cfg):
            sname = cfg.get("strategy_name","ppo")
            mpath = cfg.get("model_path","outputs/ppo_model.zip")
            tf    = cfg.get("strategy_timeframe","1min")
            _model_cache["model"] = load_model(sname)
            _last_cfg.update({
                "strategy_name": sname, "model_path": mpath, "strategy_timeframe": tf,
                "mtime": os.path.getmtime(mpath) if os.path.exists(mpath) else 0
            })
            asyncio.create_task(send_telegram(f"📈 전략/모델 갱신: {sname} ({tf})"))
        return _last_cfg
    except Exception as e:
        log_error(f"[설정/모델 로딩 실패] {e}")
        return _last_cfg

# ===== 프리플라이트 점검 =====
async def preflight_check(session: ccxt.bybit) -> bool:
    try:
        logger.info("프리플라이트 점검 시작...")
        await session.load_markets(True)
        
        logger.info("거래 가능 심볼 조회 중...")
        syms = await get_realtime_symbols(session)
        if not syms:
            await send_telegram("❌ 프리체크 실패: 거래 가능 심볼이 없습니다.")
            logger.warning("프리체크 실패: 거래 가능 심볼을 찾을 수 없습니다.")
            return False
        logger.info(f"{len(syms)}개의 거래 가능 심볼을 찾았습니다.")
        sample = "BTC/USDT:USDT" if "BTC/USDT:USDT" in syms else syms[0]

        logger.info("계정 잔고 조회 중...")
        bal = await get_balance(session, "USDT")
        if bal <= 0:
            await send_telegram("❌ 프리체크 실패: 잔고가 0입니다.")
            logger.warning(f"프리체크 실패: 계정 잔고가 0 또는 음수입니다 (잔고: {bal}).")
            return False
        logger.info(f"계정 잔고: {bal:.2f} USDT")

        logger.info(f"{sample} 캔들 데이터 조회 중...")
        df = await fetch_candles(session, sample, TF_PRIMARY, 50)
        if df.empty:
            await send_telegram(f"❌ 프리체크 실패: {sample} 캔들 없음")
            logger.warning(f"프리체크 실패: {sample} 캔들 데이터를 가져올 수 없습니다.")
            return False
        logger.info(f"{sample} 캔들 데이터 조회 완료.")

        market = session.markets[sample]
        min_qty = market.get('limits', {}).get('amount', {}).get('min')
        precision = market.get('precision', {}).get('amount')
        
        await send_telegram(f"✅ 프리체크 통과\n심볼수: {len(syms)} | 샘플: {sample}\n잔고: {bal:.2f} USDT\nminQty={min_qty} precision={precision}")
        logger.info("✅ 프리체크 통과")
        return True
    except Exception as e:
        await send_telegram(f"❌ 프리체크 예외: {e}")
        logger.error(f"[프리체크 실패] 예외 발생: {e}")
        return False


# ===== 심볼 랭킹(변동성 기반) =====
def rank_top_symbols_by_volatility(df_map: Dict[str, pd.DataFrame], top_n: int) -> List[str]:
    rows = []
    for sym, df in df_map.items():
        if len(df) < 20:
            continue
        vol = df["close"].pct_change().rolling(20).std().iloc[-1]
        rows.append({"symbol": sym, "volatility": abs(float(vol) if pd.notna(vol) else 0.0),
                     "close": float(df["close"].iloc[-1])})
    if not rows:
        return []
    md = pd.DataFrame(rows)
    md = md.sort_values("volatility", ascending=False)
    return md.head(top_n)["symbol"].tolist()

# ===== 1회 거래 루프 =====
async def run_trading_once(session: ccxt.bybit, cfg: Dict[str, Any], top_n: int = TOP_SYMBOLS_N) -> None:
    symbols = await get_realtime_symbols(session)
    if not symbols:
        await send_telegram("❌ 심볼 목록 없음 (네트워크/권한/시장 정지)")
        log_trade_csv6(now_kst_str(), "ERROR", "-", 0, 0, "심볼없음"); return

    sem = asyncio.Semaphore(MAX_PARALLEL_FETCH)
    async def _fetch(sym):
        async with sem:
            return sym, await fetch_candles(session, sym, TF_PRIMARY, 200)

    tasks = [asyncio.create_task(_fetch(sym)) for sym in symbols[:SCAN_COUNT]]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    df_map: Dict[str, pd.DataFrame] = {}
    for r in results:
        if isinstance(r, Exception):
            continue
        sym, df = r
        if isinstance(df, pd.DataFrame) and not df.empty:
            df_map[sym] = df

    if not df_map:
        await send_telegram("❌ 캔들 데이터 없음")
        log_trade_csv6(now_kst_str(), "ERROR", "-", 0, 0, "캔들없음"); return

    top_symbols = rank_top_symbols_by_volatility(df_map, top_n)
    if not top_symbols:
        # 볼륨 합계 fallback
        vol_sum = {s: float(d["volume"].tail(50).sum()) for s, d in df_map.items()}
        top_symbols = [s for s, _ in sorted(vol_sum.items(), key=lambda x: x[1], reverse=True)[:top_n]]

    for symbol in top_symbols:
        df = df_map.get(symbol, pd.DataFrame())
        if df.empty or len(df) < FEATURE_MIN_BARS:
            continue

        feats = extract_multi_timeframe_features({f"{TF_PRIMARY}": df})
        last = feats.dropna().tail(1) if isinstance(feats, pd.DataFrame) else pd.DataFrame()
        if last.empty:
            continue

        feature_dict = last.iloc[0].to_dict()
        action_info = ai_recommend_strategy_live({symbol: feature_dict})
        action = str(action_info.get("strategy", "buy")).lower()
        if action not in ("buy", "sell"):
            action = "buy"

        balance = await get_balance(session, "USDT")
        close_price = float(df["close"].iloc[-1])
        raw_qty = (balance * ORDER_RISK_PCT) / close_price if balance > MIN_BALANCE else 0.0
        
        norm_qty, market = await normalize_qty(session, symbol, raw_qty)

        now = now_kst_str()
        min_q = market.get('limits', {}).get('amount', {}).get('min', 0.0)

        if balance <= MIN_BALANCE or norm_qty < min_q:
            await send_telegram(f"❌ 수량 미달/잔고부족 – {symbol} (잔고 {balance:.2f} USDT, minQty {min_q})")
            log_trade_csv6(now, "NO_BALANCE", symbol, 0, 0, f"잔고/수량미달 minQty={min_q}")
            continue

        try:
            result = await send_order(session, symbol, action, norm_qty)
            
            order_id = result.get("id", "-")
            avg_price = float(result.get("average") or result.get("price") or 0)
            exec_qty = float(result.get("filled") or result.get("amount") or 0)
            amount_val = (avg_price or close_price) * exec_qty
            
            await send_telegram(
                f"✅ {symbol} {action.upper()} 주문 {'(DRY-RUN)' if DRY_RUN else ''}\n"
                f"🧾 주문ID: {order_id}\n수량: {exec_qty}\n추정금액: {amount_val:.2f}"
            )
            log_trade_csv6(now, action.upper(), symbol, avg_price or close_price, exec_qty,
                           f"amount={amount_val:.2f}|orderId={order_id}")
        except Exception as e:
            await send_telegram(f"❌ 주문 실패: {symbol} {action.upper()} / {norm_qty}\n사유: {e}")
            log_trade_csv6(now, "ORDER_FAIL", symbol, 0, 0, str(e))

        await safe_sleep(0.5)

    status = {
        "strategy_name": cfg.get("strategy_name"),
        "strategy_timeframe": cfg.get("strategy_timeframe"),
        "model_path": cfg.get("model_path"),
        "timestamp": now_kst_str(),
        "status": "RUNNING"
    }
    write_engine_status(status)
    try:
        generate_daily_report(status)
    except Exception as e:
        log_error(f"[일일 리포트 생성 실패] {e}")

# ===== 메인 루프 (CCXT) =====
async def main_loop():
    logger.info(f"🧩 [LIBRA] main_realtime PATCH {PATCH_VERSION} 로드됨")
    session = get_session()
    try:
        ok = await preflight_check(session)
        if not ok:
            return

        while True:
            cfg = load_and_update_model()
            try:
                await run_trading_once(session, cfg, top_n=TOP_SYMBOLS_N)
            except Exception as e:
                log_error(f"[루프 실패] {e}")
                await send_telegram(f"❌ 루프 실패: {e}")
                log_trade_csv6(now_kst_str(), "ERROR", "-", 0, 0, f"루프실패:{e}")
            await safe_sleep(5)
    finally:
        if session:
            await session.close()
            logger.info("CCXT 세션이 안전하게 종료되었습니다.")

# ===== 레버리지 설정 (CCXT) =====
async def ensure_leverage(session: ccxt.bybit, symbol: str, leverage: int) -> None:
    try:
        # CCXT는 통합 레버리지 설정을 사용
        await session.set_leverage(leverage, symbol)
        logger.info(f"✅ [{symbol}] 레버리지 {leverage}x 설정 완료")
    except Exception as e:
        log_error(f"[{symbol}] 레버리지 {leverage}x 설정 실패: {e}")

# ===== 엔트리 =====
if __name__ == "__main__":
    env_path = find_dotenv()
    if not env_path or not os.path.isfile(env_path):
        logger.warning(f"❗ .env 파일을 찾지 못했습니다. 현재 경로: {os.getcwd()}")
    load_dotenv(env_path, override=True)
    
    # 레버리지 설정 예시 (필요시 주석 해제)
    # async def setup_leverage():
    #     session = get_session()
    #     try:
    #         await ensure_leverage(session, 'BTC/USDT:USDT', 10)
    #     finally:
    #         await session.close()
    # asyncio.run(setup_leverage())

    asyncio.run(main_loop())