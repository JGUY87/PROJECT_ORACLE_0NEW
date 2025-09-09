# -*- coding: utf-8 -*-
"""
[사용 중단 모듈]

이 파일(exchange_info.py)은 더 이상 사용되지 않으며, 하위 호환성을 위해서만 유지됩니다.
이 파일의 기능은 `src.core.balance_guard.py` 모듈로 이전 및 통합되었습니다.

- **자산 잔고 조회**: `src.core.balance_guard.py`의 `get_wallet_equity_async()` 함수를 사용하세요.

새로운 개발이나 리팩토링 시에는 이 파일을 임포트하지 마십시오.
"""

import logging

logging.warning(
    "`src.core.exchange_info.py`는 더 이상 사용되지 않는 모듈입니다. "
    "대신 `src.core.balance_guard` 모듈을 사용하세요."
)