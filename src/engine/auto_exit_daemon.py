# -*- coding: utf-8 -*-
"""
src/engine/auto_exit_daemon.py — 확장버전 v2.4 (Poetry 구성 정합 리팩토링)
- 목표: 네가 제시한 pyproject.toml( Poety, ccxt/aiohttp/loguru 등 )과 100% 정합
- 의존성: ccxt, aiohttp, loguru (python-dotenv/pybit 없어도 동작)
- 기능: TP1/TP2 분할 익절, SL, 트레일링 스톱 자동 관리(비동기)
- 운영: 병렬 처리, 지수 백오프, 상태 원자 저장(JSON), 수량/가격 정밀도 반올림
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import signal
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# =========================
# (옵션) .env 로드: python-dotenv 미설치여도 통과
# =========================
def _maybe_load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except Exception:
        pass

_maybe_load_dotenv()

# =========================
# 로깅: loguru가 있으면 사용, 없으면 print
# =========================
try:
    from loguru import logger
    LOG = logger
    LOG.remove()
    LOG.add(lambda m: print(m, end=""))
except Exception:
    class _PrintLogger:
        def info(self, *a, **k): print(*a)
        def warning(self, *a, **k): print(*a)
        def error(self, *a, **k): print(*a)
    LOG = _PrintLogger()

# =========================
# 외부 라이브러리
# =========================
import aiohttp
from ccxt import NetworkError, ExchangeError
from ccxt import async_support as ccxt_async

# =========================
# 상수/환경 변수
# =========================
KST = timezone(timedelta(hours=9))
STATE_PATH = os.path.join("outputs", "auto_exit_state.json")
os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)

# 스캔/병렬/백오프
SCAN_SEC = float(os.getenv("AUTOEXIT_SCAN_SEC", "2.0"))
MAX_CONCURRENCY = int(os.getenv("AUTOEXIT_MAX_CONCURRENCY", "4"))
ERR_BACKOFF_BASE = float(os.getenv("AUTOEXIT_ERR_BACKOFF_BASE", "2.0"))  # 2,4,8..sec
ERR_BACKOFF_MAX = float(os.getenv("AUTOEXIT_ERR_BACKOFF_MAX", "60.0"))

# 브래킷(퍼센트 기반)
TP_PCT = float(os.getenv("AUTOEXIT_TP_PCT", "0.008"))          # +0.8%
SL_PCT = float(os.getenv("AUTOEXIT_SL_PCT", "0.005"))          # -0.5%
TRAIL_PCT = float(os.getenv("AUTOEXIT_TRAIL_PCT", "0.006"))    # 0.6% (hh/ll 기준)

# 분할 익절
TP1_RATIO = float(os.getenv("AUTOEXIT_TP1_RATIO", "0.5"))      # 50%
TP2_RATIO = float(os.getenv("AUTOEXIT_TP2_RATIO", "0.5"))      # 50%
TP2_EXTRA_PCT = float(os.getenv("AUTOEXIT_TP2_EXTRA_PCT", "0.004"))  # TP1 이후 추가 진전

# 대상 심볼 제한(쉼표구분, 비워두면 전체 포지션 감시)
SYMBOL_ALLOWLIST = [s.strip() for s in os.getenv("AUTOEXIT_SYMBOLS", "").split(",") if s.strip()]

# (선택) Telegram 알림 — pyproject에 telegram 라이브러리 없으므로 aiohttp로 호출
TELEGRAM_TOKEN = os.getenv("AUTOEXIT_TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("AUTOEXIT_TG_CHAT_ID", "")
ENABLE_TG = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)

# =========================
# 유틸
# =========================
def now_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def _atomic_save(path: str, obj: Any):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(tmp, path)


def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _slim_state(st: Dict[str, Any], keep: List[str]) -> Dict[str, Any]:
    slim: Dict[str, Any] = {}
    for sym in keep:
        if sym in st:
            slim[sym] = st[sym]
    return slim

# ===== 포지션/티커 유틸 =====
def _pos_contracts(p: Dict[str, Any]) -> float:
    for k in ("contracts", "contractSize", "size", "amount", "positionAmt", "qty"):
        v = p.get(k)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0


def _pos_side(p: Dict[str, Any]) -> str:
    side = (p.get("positionSide") or p.get("side") or p.get("direction") or "").lower()
    if side in ("long", "short"):
        return side
    qty = _pos_contracts(p)
    return "long" if qty > 0 else ("short" if qty < 0 else "")


def _pos_entry_price(p: Dict[str, Any]) -> float:
    for k in ("entryPrice", "avgPrice", "entry_price", "average", "markPrice", "avgEntryPrice"):
        v = p.get(k)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0


def _pos_tp(p: Dict[str, Any]) -> float:
    for k in ("takeProfit", "takeProfitPrice", "tp", "tpPrice"):
        v = p.get(k)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0


def _pos_sl(p: Dict[str, Any]) -> float:
    for k in ("stopLoss", "stopLossPrice", "sl", "slPrice"):
        v = p.get(k)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return 0.0


def _ticker_last(t: Dict[str, Any]) -> float:
    for k in ("last", "close", "price"):
        v = t.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    info = t.get("info")
    if isinstance(info, dict):
        for k in ("last", "close", "price"):
            v = info.get(k)
            if isinstance(v, (int, float)):
                return float(v)
    return float("nan")


# ===== 정밀도 반올림 =====
def _round_amount(market: Dict[str, Any], amount: float) -> float:
    if amount <= 0:
        return 0.0
    prec = (market.get("precision") or {}).get("amount")
    step = ((market.get("limits") or {}).get("amount") or {}).get("step")
    min_amt = ((market.get("limits") or {}).get("amount") or {}).get("min")

    amt = float(amount)
    if isinstance(prec, (int, float)) and prec >= 0:
        q = 10 ** int(prec)
        amt = round(amt * q) / q
    if isinstance(step, (int, float)) and step > 0:
        k = round(amt / step)
        amt = float(k * step)
    if isinstance(min_amt, (int, float)) and min_amt > 0 and amt < min_amt:
        amt = float(min_amt)
    return max(0.0, amt)


def _round_price(market: Dict[str, Any], price: float) -> float:
    if price <= 0:
        return 0.0
    prec = (market.get("precision") or {}).get("price")
    step = ((market.get("limits") or {}).get("price") or {}).get("step")
    p = float(price)
    if isinstance(prec, (int, float)) and prec >= 0:
        q = 10 ** int(prec)
        p = round(p * q) / q
    if isinstance(step, (int, float)) and step > 0:
        k = round(p / step)
        p = float(k * step)
    return max(0.0, p)


def _tp_targets(side: str, entry: float, market: Optional[Dict[str, Any]] = None) -> Tuple[float, float, float]:
    """
    반환: (tp1, tp2, sl)
    - tp1: TP_PCT 적용
    - tp2: tp1 대비 추가 진전(TP2_EXTRA_PCT) 적용 (롱=상향, 숏=하향)
    - sl : SL_PCT 적용
    """
    if side == "long":
        tp1 = entry * (1 + TP_PCT)
        tp2 = tp1 * (1 + TP2_EXTRA_PCT)
        sl = entry * (1 - SL_PCT)
    else:
        tp1 = entry * (1 - TP_PCT)
        tp2 = tp1 * (1 - TP2_EXTRA_PCT)
        sl = entry * (1 + SL_PCT)

    if market:
        tp1 = _round_price(market, tp1)
        tp2 = _round_price(market, tp2)
        sl = _round_price(market, sl)
    else:
        tp1, tp2, sl = round(tp1, 8), round(tp2, 8), round(sl, 8)

    return tp1, tp2, sl


# =========================
# CCXT 비동기 클라이언트
# =========================
async def get_ccxt_client() -> ccxt_async.Exchange:
    """CCXT 비동기 클라이언트 생성 및 마켓 메타 로드 (Bybit 무기한 기본)"""
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    is_testnet = os.getenv("BYBIT_TESTNET", os.getenv("BYBIT_USE_TESTNET", "false")).lower() == "true"

    if not api_key or not api_secret:
        raise RuntimeError("BYBIT_API_KEY 또는 BYBIT_API_SECRET 환경 변수가 설정되지 않았습니다.")

    exchange_class = getattr(ccxt_async, "bybit")
    client = exchange_class(
        {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",
                "testnet": is_testnet,
            },
        }
    )
    await client.load_markets()
    return client


# =========================
# 브래킷/트레일 설정(거래소별 폴백)
# =========================
async def _try_edit_position(client: ccxt_async.Exchange, symbol: str, params: Dict[str, Any]) -> bool:
    fn = getattr(client, "edit_position", None)
    if callable(fn):
        await fn(symbol=symbol, params=params)  # type: ignore
        return True
    return False


async def _try_order_with_params(client: ccxt_async.Exchange, symbol: str, side: str, params: Dict[str, Any]) -> bool:
    try:
        await client.create_order(symbol=symbol, type="market", side=side, amount=0, params=params)
        return True
    except Exception:
        return False


async def ensure_bracket(client: ccxt_async.Exchange, symbol: str, side: str, entry: float):
    """포지션에 TP/SL 브라켓이 없으면 설정"""
    try:
        positions = await client.fetch_positions(symbols=[symbol])
        pos = next(
            (p for p in (positions or []) if p.get("symbol") == symbol and _pos_contracts(p) != 0 and _pos_side(p) == side),
            None,
        )
        if not pos:
            return

        market = (client.markets or {}).get(symbol) or {}
        tp1_price, _, sl_price = _tp_targets(side, entry, market)
        cur_tp, cur_sl = _pos_tp(pos), _pos_sl(pos)
        if cur_tp > 0 and cur_sl > 0:
            return

        params: Dict[str, Any] = {}
        if cur_tp <= 0: params["takeProfit"] = tp1_price
        if cur_sl <= 0: params["stopLoss"]   = sl_price
        if not params:
            return

        # 1) CCXT edit_position
        if await _try_edit_position(client, symbol, params):
            LOG.info(f"[{now_kst()}] [{symbol}] TP/SL 설정 완료(edit): {params}")
            return

        # 2) 폴백: order params
        side_for_order = "sell" if side == "long" else "buy"
        if await _try_order_with_params(client, symbol, side_for_order, params):
            LOG.info(f"[{now_kst()}] [{symbol}] TP/SL 설정 완료(order-params): {params}")
            return

        LOG.warning(f"[{now_kst()}] [{symbol}] TP/SL 설정 미지원(거래소/버전)")
    except ExchangeError as e:
        LOG.error(f"[{now_kst()}] [{symbol}] 브래킷 설정 거래소 오류: {e}")
    except Exception as e:
        LOG.error(f"[{now_kst()}] [{symbol}] 브래킷 설정 예외: {e}")


async def fire_partial_take_profit(
    client: ccxt_async.Exchange,
    symbol: str,
    side: str,
    portion: str,
    qty: float,
) -> Optional[Dict[str, Any]]:
    """부분 익절 실행 (TP1/TP2) — 수량/정밀도 규격 맞춤"""
    if qty <= 0:
        return None

    try:
        market = (client.markets or {}).get(symbol) or {}
    except Exception:
        market = {}

    order_side = "sell" if side == "long" else "buy"
    adj_qty = _round_amount(market, qty)
    if adj_qty <= 0:
        LOG.warning(f"[{now_kst()}] [{symbol}] {portion} 익절 스킵: 수량<규격(min/step)")
        return None

    try:
        res = await client.create_order(
            symbol=symbol,
            type="market",
            side=order_side,
            amount=adj_qty,
            params={"reduceOnly": True},
        )
        LOG.info(f"[{now_kst()}] [{symbol}] {portion} 익절 실행: {adj_qty} {order_side}")
        return res
    except Exception as e:
        LOG.error(f"[{now_kst()}] [{symbol}] {portion} 익절 실패: {e}")
        return None


async def trail_update(client: ccxt_async.Exchange, symbol: str, side: str, state: Dict[str, Any]):
    """트레일링 스톱 업데이트 — hh/ll 기준 SL 갱신"""
    try:
        positions = await client.fetch_positions(symbols=[symbol])
        pos = next(
            (p for p in (positions or []) if p.get("symbol") == symbol and _pos_contracts(p) != 0 and _pos_side(p) == side),
            None,
        )
        if not pos:
            return

        market = (client.markets or {}).get(symbol) or {}

        if side == "long":
            ref = float(state.get("hh", 0.0))
            if ref <= 0:
                return
            target_sl = _round_price(market, ref * (1 - TRAIL_PCT))
        else:
            ll_raw = state.get("ll", None)
            if ll_raw is None:
                return
            ref = float(ll_raw)
            target_sl = _round_price(market, ref * (1 + TRAIL_PCT))

        cur_sl = _pos_sl(pos)
        if cur_sl > 0 and abs(cur_sl - target_sl) < 1e-12:
            return

        params = {"stopLoss": target_sl}

        # 1) CCXT edit_position
        if await _try_edit_position(client, symbol, params):
            LOG.info(f"[{now_kst()}] [{symbol}] 트레일링 SL 업데이트(edit): {target_sl}")
            return

        # 2) 폴백: order params
        side_for_order = "sell" if side == "long" else "buy"
        if await _try_order_with_params(client, symbol, side_for_order, params):
            LOG.info(f"[{now_kst()}] [{symbol}] 트레일링 SL 업데이트(order-params): {target_sl}")
            return

        LOG.warning(f"[{now_kst()}] [{symbol}] 트레일링 SL 업데이트 미지원(거래소/버전)")
    except ExchangeError as e:
        LOG.error(f"[{now_kst()}] [{symbol}] 트레일링 거래소 오류: {e}")
    except Exception as e:
        LOG.error(f"[{now_kst()}] [{symbol}] 트레일링 예외: {e}")


# =========================
# Telegram 알림 (선택)
# =========================
async def tg_notify(session: aiohttp.ClientSession, text: str) -> None:
    if not ENABLE_TG:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                LOG.warning(f"Telegram 응답 비정상: {resp.status}")
    except Exception as e:
        LOG.warning(f"Telegram 전송 실패: {e}")


# =========================
# 심볼별 워커
# =========================
async def handle_symbol(
    client: ccxt_async.Exchange,
    symbol: str,
    st: Dict[str, Any],
    backoffs: Dict[str, int],
    session: Optional[aiohttp.ClientSession] = None,
):
    step = backoffs.get(symbol, 0)
    if step > 0:
        delay = min(ERR_BACKOFF_BASE**step, ERR_BACKOFF_MAX)
        await asyncio.sleep(delay)

    try:
        positions = await client.fetch_positions(symbols=[symbol])
        pos = next((p for p in (positions or []) if p.get("symbol") == symbol and _pos_contracts(p) != 0), None)
        if not pos:
            backoffs[symbol] = 0
            return

        side = _pos_side(pos)
        entry = _pos_entry_price(pos)
        qty = _pos_contracts(pos)
        if side not in ("long", "short") or entry <= 0 or qty == 0:
            backoffs[symbol] = 0
            return

        sym_st = st.get(symbol, {"hh": 0.0, "ll": None, "tp1_done": False, "tp2_done": False, "last_tp_ts": 0})

        # 현재가
        try:
            tkr = await client.fetch_ticker(symbol)
            last_price = float(_ticker_last(tkr))
        except Exception:
            last_price = float("nan")

        # HH/LL 갱신
        if last_price == last_price:  # not NaN
            if side == "long":
                if last_price > float(sym_st.get("hh", 0.0)):
                    sym_st["hh"] = last_price
            else:
                base_ll = sym_st.get("ll", None)
                if base_ll is None or last_price < float(base_ll):
                    sym_st["ll"] = last_price

        # 브래킷 보정
        await ensure_bracket(client, symbol, side, entry)

        # 목표가
        market = (client.markets or {}).get(symbol) or {}
        tp1_price, tp2_price, _ = _tp_targets(side, entry, market)

        # 더블 파이어 방지
        fired_now = False

        # TP1
        if not sym_st.get("tp1_done", False):
            hit1 = (side == "long" and last_price >= tp1_price) or (side == "short" and last_price <= tp1_price)
            if hit1:
                q1 = max(qty * TP1_RATIO, 0.0)
                if await fire_partial_take_profit(client, symbol, side, "TP1", q1):
                    sym_st["tp1_done"] = True
                    sym_st["last_tp_ts"] = datetime.now(KST).timestamp()
                    fired_now = True
                    await tg_notify(session, f"[TP1] {symbol} {side} q={q1} @~{last_price}")

        # TP2 (추가 진전 목표)
        if (not fired_now) and sym_st.get("tp1_done", False) and not sym_st.get("tp2_done", False):
            hit2 = (side == "long" and last_price >= tp2_price) or (side == "short" and last_price <= tp2_price)
            if hit2:
                q2 = max(qty * TP2_RATIO, 0.0)
                if await fire_partial_take_profit(client, symbol, side, "TP2", q2):
                    sym_st["tp2_done"] = True
                    sym_st["last_tp_ts"] = datetime.now(KST).timestamp()
                    fired_now = True
                    await tg_notify(session, f"[TP2] {symbol} {side} q={q2} @~{last_price}")

        # 트레일링
        await trail_update(client, symbol, side, sym_st)

        # 상태 저장 & 백오프 초기화
        st[symbol] = sym_st
        backoffs[symbol] = 0

    except (NetworkError, ExchangeError) as e:
        LOG.error(f"[{now_kst()}] [{symbol}] 심볼 처리 중 거래소/네트워크 오류: {e}")
        await tg_notify(session, f"[ERR] {symbol} 거래소/네트워크 오류: {e}")
        backoffs[symbol] = backoffs.get(symbol, 0) + 1
    except Exception as e:
        LOG.error(f"[{now_kst()}] [{symbol}] 심볼 처리 예외: {e}")
        await tg_notify(session, f"[ERR] {symbol} 예외: {e}")
        backoffs[symbol] = backoffs.get(symbol, 0) + 1


# =========================
# 메인 루프
# =========================
async def run():
    client = await get_ccxt_client()

    stop_event = asyncio.Event()

    def _signal_handler(*_):
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    backoffs: Dict[str, int] = {}
    async with aiohttp.ClientSession() as session:
        try:
            while not stop_event.is_set():
                try:
                    positions = await client.fetch_positions()
                    symbols = sorted(
                        {
                            p.get("symbol")
                            for p in (positions or [])
                            if _pos_contracts(p) != 0
                            and (not SYMBOL_ALLOWLIST or p.get("symbol") in SYMBOL_ALLOWLIST)
                        }
                    )
                    state = _load_state()

                    sem = asyncio.Semaphore(MAX_CONCURRENCY)

                    async def _worker(sym: str):
                        async with sem:
                            await handle_symbol(client, sym, state, backoffs, session=session)

                    await asyncio.gather(*[_worker(sym) for sym in symbols])

                    _atomic_save(STATE_PATH, _slim_state(state, symbols))

                except NetworkError as e:
                    LOG.error(f"[{now_kst()}] 네트워크 오류: {e}")
                    await tg_notify(session, f"[ERR] 네트워크 오류: {e}")
                except ExchangeError as e:
                    LOG.error(f"[{now_kst()}] 거래소 오류: {e}")
                    await tg_notify(session, f"[ERR] 거래소 오류: {e}")
                except Exception as e:
                    LOG.error(f"[{now_kst()}] 루프 예외: {e}")
                    await tg_notify(session, f"[ERR] 루프 예외: {e}")

                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=SCAN_SEC)
                except asyncio.TimeoutError:
                    pass
        finally:
            try:
                await client.close()
            except Exception:
                pass


def _maybe_enable_uvloop():
    try:
        if platform.system() != "Windows":
            import uvloop  # type: ignore
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            LOG.info("[uvloop] 활성화")
    except Exception:
        pass


if __name__ == "__main__":
    _maybe_enable_uvloop()
    # Poetry 레이아웃: python -m src.engine.auto_exit_daemon
    asyncio.run(run())
