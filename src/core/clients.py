# -*- coding: utf-8 -*-
"""
거래소 API 클라이언트 생성 모듈 (호환성 유지용)

[경고] 이 모듈은 더 이상 사용되지 않습니다 (Deprecated).
대신 `src.core.bybit_router`의 `get_bybit_client` 함수를 직접 사용하세요.
이 파일은 기존 코드와의 호환성을 위해 임시로 유지됩니다.
"""
import logging
from .bybit_router import get_bybit_client

# 경고 메시지 한 번만 출력하기 위한 플래그
_deprecation_warning_logged = False

async def get_exchange_client():
    """
    [Deprecated] Bybit 클라이언트를 반환합니다.
    
    실제 로직은 `bybit_router.get_bybit_client`를 호출합니다.
    """
    global _deprecation_warning_logged
    if not _deprecation_warning_logged:
        logging.warning(
            "`get_exchange_client` 함수는 더 이상 사용되지 않습니다. "
            "`get_bybit_client`를 대신 사용하세요."
        )
        _deprecation_warning_logged = True
    
    return await get_bybit_client()
