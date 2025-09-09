# -*- coding: utf-8 -*-
"""
core/order_preflight.py
------------------------------------
📌 목적: Bybit v5 (USDT 선물, category='linear', accountType='UNIFIED') 주문 전 프리플라이트(가용잔고/수량/수수료/버퍼) 체크 및
        수량 자동 축소(snap) 기능 제공.
- ErrCode 110007("ab not enough for new order") 방지
- 최소/스텝/최대 수량 규격 자동 보정
- 레버리지·수수료·버퍼 반영한 '필요 증거금' 계산
- 초보/외주 개발자도 바로 적용할 수 있도록 한글 주석 포함

✅ 통합 방식(권장)
1) 심볼 정보: market/instruments-info에서 lotSizeFilter.qtyStep, minOrderQty, maxOrderQty 확보
2) 잔고: account/wallet-balance (accountType=UNIFIED) → availableBalance
3) 호가/가격: 주문 직전 최신가(lastPrice) 또는 매수/매도호가
4) 아래 함수 preflight_and_resize_qty(...) 호출 → (최종수량, 진단문구) 반환
5) 최종수량이 0이면 주문 중단 + 텔레그램 알림
6) 0보다 크면 해당 수량으로 주문 실행

🧮 필요 증거금(근사치)
required ≈ notional/leverage + notional*(taker_fee + buffer)
- notional = price * qty
- taker_fee(기본 0.0006), buffer(기본 0.001~0.003 권장)

⚠️ 주의
- 최초 심볼 거래 시 반드시 /v5/position/set-leverage 선행 설정!
- 교차/격리, 위험한도, 활동중 포지션과의 상호작용에 따라 실제 필요 증거금은 더 클 수 있음.
"""

from decimal import Decimal, ROUND_DOWN


def _to_decimal(x):
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def snap_qty(qty, step, min_qty=None, max_qty=None):
    """
    수량을 거래소 규격에 맞춰 '내림' 스냅. (과주문 방지)
    """
    q = _to_decimal(qty)
    st = _to_decimal(step) if step is not None else Decimal("0")
    if st > 0:
        q = (q / st).to_integral_exact(rounding=ROUND_DOWN) * st
    if min_qty is not None:
        mq = _to_decimal(min_qty)
        if q < mq:
            return Decimal("0")
    if max_qty is not None:
        M = _to_decimal(max_qty)
        if q > M:
            q = M
    # 소수자릿수 정리 (표시용)
    return q.normalize()


def estimate_required_margin(price, qty, leverage=10, taker_fee=Decimal("0.0006"), buffer=Decimal("0.001")):
    """
    가격/수량/레버리지/수수료/버퍼를 반영한 필요 증거금(근사) 계산
    """
    p = _to_decimal(price)
    q = _to_decimal(qty)
    L = _to_decimal(leverage)
    fee = _to_decimal(taker_fee)
    buf = _to_decimal(buffer)

    notional = p * q
    # IM(초기증거금) + 수수료 + 버퍼
    required = (notional / L) + (notional * (fee + buf))
    return required, notional


def max_affordable_qty(available_balance, price, leverage=10, taker_fee=Decimal("0.0006"), buffer=Decimal("0.001")):
    """
    가용잔고로 살 수 있는 최대 수량(근사)을 역산.
    available >= price*qty*(1/leverage + fee + buffer)
    ⇒ qty_max = available / (price*(1/leverage + fee + buffer))
    """
    ab = _to_decimal(available_balance)
    p = _to_decimal(price)
    L = _to_decimal(leverage)
    fee = _to_decimal(taker_fee)
    buf = _to_decimal(buffer)

    denom = p * ((Decimal("1") / L) + fee + buf)
    if denom <= 0:
        return Decimal("0")
    qty_max = ab / denom
    return qty_max if qty_max > 0 else Decimal("0")


def preflight_and_resize_qty(
    qty_requested,
    price,
    available_balance,
    leverage=10,
    taker_fee=Decimal("0.0006"),
    buffer=Decimal("0.0015"),
    step=Decimal("0.001"),
    min_qty=Decimal("0.001"),
    max_qty=None,
):
    """
    1) 잔고 기준 최대 가능 수량 계산
    2) 요청수량과 규격/한도를 반영해 안전 수량 산출
    3) 최종 수량=0이면 주문 중단 사유 반환
    """
    # 1) 잔고로 가능한 최대 수량(근사)
    qty_ab_max = max_affordable_qty(available_balance, price, leverage, taker_fee, buffer)

    # 2) 요청 수량과 교차
    target = min(_to_decimal(qty_requested), qty_ab_max)
    # 3) 규격 스냅
    target = snap_qty(target, step, min_qty=min_qty, max_qty=max_qty)

    # 4) 최종 진단
    required, notional = estimate_required_margin(price, target, leverage, taker_fee, buffer)

    diagnosis = {
        "requested_qty": str(qty_requested),
        "snapped_final_qty": str(target),
        "price": str(price),
        "leverage": str(leverage),
        "available_balance": str(available_balance),
        "notional": str(notional),
        "estimated_required_margin": str(required),
        "taker_fee": str(taker_fee),
        "buffer": str(buffer),
        "step": str(step),
        "min_qty": str(min_qty),
        "max_qty": str(max_qty) if max_qty is not None else None,
        "reason": None,
    }

    if target == 0:
        # 최소수량 미만/잔고부족 등
        need_qty = snap_qty(min_qty, step, min_qty=min_qty)
        # 최소 주문에 필요한 근사 증거금
        min_required, min_notional = estimate_required_margin(price, need_qty, leverage, taker_fee, buffer)
        diagnosis["reason"] = (
            f"가용잔고 부족 또는 최소수량 미만. 최소 주문 필요 증거금≈{min_required:.6f} USDT, "
            f"가용잔고={available_balance}. 레버리지={leverage}, 수수료={taker_fee}, 버퍼={buffer}"
        )
    else:
        diagnosis["reason"] = "OK"

    return target, diagnosis


# === 사용 예시 ===
if __name__ == "__main__":
    # 가상의 예시: 가격 60,000 USDT인 BTCUSDT, 레버리지 10배, 가용잔고 50 USDT, 수수료 0.06%, 버퍼 0.15%
    qty, info = preflight_and_resize_qty(
        qty_requested=Decimal("0.01"),
        price=Decimal("60000"),
        available_balance=Decimal("50"),
        leverage=10,
        taker_fee=Decimal("0.0006"),
        buffer=Decimal("0.0015"),
        step=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        max_qty=None
    )
    print(qty, info)
