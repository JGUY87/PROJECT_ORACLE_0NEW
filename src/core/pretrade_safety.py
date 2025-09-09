# -*- coding: utf-8 -*-

# `pretrade_safety.py` 파일을 생성하는 Python 코드 🧩

import os

# 파일 내용 (여기에 전체 pretrade_safety.py 내용이 들어갑니다)
file_content = """# -*- coding: utf-8 -*-
\\\"\\\"
src/core/pretrade_safety.py
============================================================
📌 목적
- 주문 전 안전성 검사 및 **잔고 부족 시 자동 감량 재시도** (CCXT 기반)
- qtyStep/minOrderQty 보정과 함께 **시장가 주문 안전 래핑**
============================================================
\\\"\\\"
from __future__ import annotations
import math
import time
from typing import Dict, Any, Tuple
import ccxt  # 🧰 ccxt 임포트

# CCXT 에러 코드 (Bybit 특정 에러 코드 대신 CCXT 공통 에러 사용)
# ccxt.InsufficientFunds, ccxt.InvalidOrder, ccxt.ExchangeError 등
# INSUFFICIENT_CODES = {\\\"110007\\\"} # 기존 pybit 코드 (사용 안 함)

def _reduce_qty(qty: float, rate: float = 0.9, min_qty: float = 0.0, step: float = 0.0) -> float:
    \\\"\\\"
    주문 수량을 지정된 비율로 감소시키고, 최소 수량 및 스텝에 맞춰 조정합니다.
    Args:
        qty (float): 현재 수량.
        rate (float): 감소 비율 (예: 0.9는 10% 감소).
        min_qty (float): 최소 주문 수량.
        step (float): 수량 스텝.
    Returns:
        float: 조정된 수량.
    \\\"\\\"
    q = max(qty * rate, min_qty)
    if step and step > 0:
        q = math.floor(q / step) * step
    return max(q, min_qty)

def safe_market_order(
    client: ccxt.Exchange, *,
    symbol: str,
    side: str,
    qty: float,
    reduce_only: bool=False,
    position_idx: int=0,  # position_idx는 ccxt에서 직접 사용되지 않음
    max_retries: int = 3
) -> Dict[str, Any]:
    \\\"\\\"
    🛡️ 시장가 주문 안전 래퍼 (CCXT 기반)
    - 잔고 부족 등 특정 에러 발생 시 수량 감소 후 재시도
    Args:
        client (ccxt.Exchange): CCXT 거래소 클라이언트 객체.
        symbol (str): 거래 심볼 (예: 'BTC/USDT:USDT').
        side (str): 주문 방향 ('buy' 또는 'sell').
        qty (float): 주문 수량.
        reduce_only (bool): 포지션 축소만 허용 여부.
        max_retries (int): 최대 재시도 횟수.
    Returns:
        Dict[str, Any]: 주문 결과.
    \\\"\\\"
    # 심볼 정보 가져오기 (ccxt)
    # client.load_markets()  # 마켓 정보 로드 (필요시)
    market = client.market(symbol)
    step = market['limits']['amount']['min']  # 🔢 최소 주문 수량 (스텝 대용)
    min_qty = market['limits']['amount']['min']  # ✅ 최소 주문 수량

    # 1차 시도 수량 보정
    q = max(qty, min_qty)

    for attempt in range(max_retries + 1):
        try:
            params = {'reduceOnly': reduce_only}
            # CCXT 통합 주문 API 사용
            order = client.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=q,
                params=params
            )
            return order  # ✅ 성공 시 주문 결과 반환
        except ccxt.InsufficientFunds as e:
            # 잔고 부족 오류 시 수량 감소 후 재시도
            print(f\"잔고 부족 오류 발생 (시도 {attempt+1}/{max_retries+1}): {e}\")
            q = _reduce_qty(q, rate=0.9, min_qty=min_qty, step=step)
            if q <= 0 or (q == min_qty and attempt == max_retries):
                print(\"최소 수량 이하 또는 최대 재시도 횟수 도달. 주문 실패.\")
                return {\"retCode\": -1, \"retMsg\": f\"Insufficient funds after retries: {e}\"}
            continue  # 🔁 다음 재시도
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
            # 네트워크 또는 거래소 오류 시 재시도 (선택적)
            print(f\"네트워크/거래소 오류 발생 (시도 {attempt+1}/{max_retries+1}): {e}\")
            if attempt == max_retries:
                print(\"최대 재시도 횟수 도달. 주문 실패.\")
                return {\"retCode\": -1, \"retMsg\": f\"Network/Exchange error after retries: {e}\"}
            time.sleep(1)  # ⏳ 잠시 대기 후 재시도
            continue
        except ccxt.ExchangeError as e:
            # 기타 거래소 오류 (예: InvalidOrder)
            print(f\"거래소 오류 발생: {e}\")
            return {\"retCode\": -1, \"retMsg\": f\"Exchange error: {e}\"}
        except Exception as e:
            # 예상치 못한 기타 오류
            print(f\"예상치 못한 오류 발생: {e}\")
            return {\"retCode\": -1, \"retMsg\": f\"Unexpected error: {e}\"}

    return {\"retCode\": -1, \"retMsg\": \"Max retries reached without successful order.\"}  # ❌ 모든 재시도 실패 시
"""

# 파일이 생성될 경로 (새 프로젝트 폴더의 src/core)
file_path = os.path.join(os.environ.get('TEMP', ''), 'PROJECT_ORACLE_0_NEW', 'src', 'core', 'pretrade_safety.py')

# 디렉토리가 없으면 생성
os.makedirs(os.path.dirname(file_path), exist_ok=True)

try:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(file_content)
    print(f"✅ 파일이 성공적으로 생성되었습니다: {file_path}")
except Exception as e:
    print(f"⚠️ 파일 생성 중 오류 발생: {e}")
