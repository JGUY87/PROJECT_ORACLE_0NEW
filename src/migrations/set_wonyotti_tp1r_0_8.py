# -*- coding: utf-8 -*-
"""
기존 strategy_overrides.json에 wonyotti.tp1_r=0.8을 병합 추가
"""
import json
from pathlib import Path
import logging

# 로거 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 경로 설정
OVERRIDES_FILE = Path(__file__).parent.parent / "configs" / "strategy_overrides.json"

def merge_wonyotti_setting():
    """
    strategy_overrides.json 파일을 읽어 'wonyotti' 전략에 'tp1_r' 값을 0.8로 설정하거나 업데이트합니다.
    파일이나 상위 객체가 없으면 새로 생성합니다.
    """
    data = {}
    try:
        if OVERRIDES_FILE.exists():
            try:
                data = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logging.warning(f"경고: '{OVERRIDES_FILE}' 파일이 비어있거나 유효한 JSON이 아닙니다. 새로 생성합니다.")
                data = {}
        else:
            logging.info(f"'{OVERRIDES_FILE}' 파일이 없어 새로 생성합니다.")
            # Ensure the parent directory exists
            OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)


        # 'strategies' 딕셔너리가 없거나 타입이 올바르지 않으면 초기화
        if "strategies" not in data or not isinstance(data.get("strategies"), dict):
            data["strategies"] = {}

        # 'wonyotti' 딕셔너리가 없거나 타입이 올바르지 않으면 초기화
        if "wonyotti" not in data["strategies"] or not isinstance(data["strategies"].get("wonyotti"), dict):
            data["strategies"]["wonyotti"] = {}

        # 'tp1_r' 값 설정 또는 업데이트
        data["strategies"]["wonyotti"]["tp1_r"] = 0.8

        # 변경된 내용을 파일에 쓰기
        OVERRIDES_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=4),
            encoding="utf-8"
        )
        logging.info(f"성공: '{OVERRIDES_FILE}' 파일에 'wonyotti' 전략의 'tp1_r' 값을 0.8로 설정했습니다.")

    except Exception as e:
        logging.error(f"'{OVERRIDES_FILE}' 파일 처리 중 오류 발생: {e}", exc_info=True)

if __name__ == "__main__":
    merge_wonyotti_setting()