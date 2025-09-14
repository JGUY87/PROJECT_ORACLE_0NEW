# -*- coding: utf-8 -*-
"""
구버전 settings.json의 키를 v3 스키마로 승격하는 마이그레이션 스크립트
"""
import json
from pathlib import Path
import logging

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 경로 설정 (스크립트 위치 기반)
# src/migrations/2025-08-13_v3_migrate.py -> configs/settings.json
SETTINGS_FILE = Path(__file__).parent.parent / "configs" / "settings.json"

def migrate_settings_to_v3():
    """
    settings.json 파일을 v3 스키마로 마이그레이션합니다.
    - 'engine' 객체 생성
    - 'risk' 객체 추가
    - 'telegram' 객체 추가
    """
    if not SETTINGS_FILE.exists():
        logging.warning(f"마이그레이션할 설정 파일({SETTINGS_FILE})을 찾을 수 없습니다.")
        return

    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logging.error(f"설정 파일({SETTINGS_FILE}) 파싱 실패: {e}. 마이그레이션을 건너뜁니다.")
        return
    except Exception as e:
        logging.error(f"설정 파일({SETTINGS_FILE})을 읽는 중 오류 발생: {e}")
        return

    made_changes = False

    # 1. 'engine' 객체 마이그레이션
    if "strategy" in settings and "engine" not in settings:
        logging.info("v2 -> v3: 'engine' 객체를 생성합니다.")
        engine_config = {
            "strategy": settings.pop("strategy"),
            "symbol": settings.pop("symbol", "BTC/USDT"),
            "timeframe": settings.pop("timeframe", "1m"),
            "category": "linear",
            "accountType": "UNIFIED",
            "is_testnet": settings.pop("testnet", False)
        }
        settings["engine"] = engine_config
        made_changes = True

    # 2. 'risk' 객체 추가 (없는 경우)
    if "risk" not in settings:
        logging.info("v2 -> v3: 기본 'risk' 객체를 추가합니다.")
        settings["risk"] = {
            "max_leverage": 10,
            "daily_loss_cut_pct": 0.07,
            "per_trade_risk_pct": 0.01,
            "max_concurrent_positions": 1
        }
        made_changes = True
        
    # 3. 'telegram' 객체 추가 (없는 경우)
    if "telegram" not in settings:
        logging.info("v2 -> v3: 기본 'telegram' 객체를 추가합니다.")
        settings["telegram"] = {
            "enabled": True,
            "token": "YOUR_TELEGRAM_BOT_TOKEN",
            "chat_id": "YOUR_TELEGRAM_CHAT_ID"
        }
        made_changes = True

    if not made_changes:
        logging.info("설정 파일이 이미 최신 v3 스키마입니다. 마이그레이션이 필요 없습니다.")
        return

    try:
        SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=4), encoding="utf-8")
        logging.info(f"성공: 설정 파일({SETTINGS_FILE})이 v3 형식으로 마이그레이션되었습니다.")
    except Exception as e:
        logging.error(f"마이그레이션된 설정 파일 저장 실패: {e}")

if __name__ == "__main__":
    migrate_settings_to_v3()