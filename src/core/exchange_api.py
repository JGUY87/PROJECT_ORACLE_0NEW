# -*- coding: utf-8 -*-
"""
[사용 중단 모듈]

이 파일(exchange_api.py)은 더 이상 사용되지 않으며, 하위 호환성을 위해서만 유지됩니다.
이 파일의 기능은 다음과 같은 새로운 모듈로 이전 및 통합되었습니다.

- **API 클라이언트 관리**: `src.core.bybit_router.py`
  - `get_bybit_client()`를 사용하여 중앙에서 관리되는 비동기 CCXT 클라이언트를 가져오세요.

- **데이터 로딩 및 캐싱**: `src.core.data_manager.py`
  - `fetch_ohlcv()`를 사용하여 OHLCV 데이터를 로드하고 캐싱하세요.

- **잔고 확인**: `src.core.balance_guard.py`
  - `get_wallet_equity_async()` 및 `can_trade_async()`를 사용하여 잔고를 확인하세요.

- **주문 실행 및 기타 API 호출**:
  - `get_bybit_client()`로 얻은 CCXT 클라이언트 객체의 표준 메소드(예: `create_market_order()`, `fetch_ticker()` 등)를 직접 사용하세요.

새로운 개발이나 리팩토링 시에는 이 파일을 임포트하지 마십시오.
"""

import logging

logging.warning(
    "`src.core.exchange_api.py`는 더 이상 사용되지 않는 모듈입니다. "
    "대신 `bybit_router`, `data_manager` 등의 모듈을 직접 사용하세요."
)