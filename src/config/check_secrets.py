# -*- coding: utf-8 -*- 
"""환경 변수 및 설정 파일의 유효성을 검사하는 헬퍼 스크립트."""
import os
from pathlib import Path
from dotenv import load_dotenv

# --- 설정 ---
# 프로젝트 루트 디렉토리 (이 파일의 상위 3단계)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# 필수 환경 변수 목록
REQUIRED_ENV_VARS = [
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID"
]

# 확인할 설정 파일 목록
CONFIG_FILES = [
    "configs/accounts.json",
    "configs/settings.json"
]

def check_secrets():
    """환경 변수와 설정 파일의 유효성을 검사하고 결과를 출력합니다."""
    print("=================================================")
    print("🔑 민감 정보 및 설정 파일 검사를 시작합니다.")
    print(f"📁 프로젝트 루트: {ROOT_DIR}")
    print("=================================================")

    all_ok = True

    # 1. .env 파일 로드 및 환경 변수 검사
    print("\n--- 1. .env 파일 및 환경 변수 검사 ---")
    dotenv_path = ROOT_DIR / ".env"
    if dotenv_path.exists():
        print(f"✅ '{dotenv_path}' 파일을 찾았습니다. 내용을 검사합니다.")
        load_dotenv(dotenv_path=dotenv_path)
    else:
        print(f"⚠️ '{dotenv_path}' 파일을 찾을 수 없습니다. 환경 변수가 시스템에 직접 설정되어 있어야 합니다.")
        all_ok = False

    for var in REQUIRED_ENV_VARS:
        value = os.getenv(var)
        if not value or value.upper().startswith("YOUR_"):
            print(f"❌ [필수] '{var}' 환경 변수가 설정되지 않았거나 기본값입니다.")
            all_ok = False
        else:
            print(f"✅ '{var}' 환경 변수가 올바르게 설정되었습니다.")

    # 2. 설정 파일 존재 여부 검사
    print("\n--- 2. 주요 설정 파일 존재 여부 검사 ---")
    for config_file in CONFIG_FILES:
        file_path = ROOT_DIR / config_file
        if file_path.exists():
            print(f"✅ 설정 파일 '{file_path}'이(가) 존재합니다.")
        else:
            print(f"❌ [필수] 설정 파일 '{file_path}'을(를) 찾을 수 없습니다.")
            all_ok = False

    # --- 최종 결과 ---
    print("\n-------------------------------------------------")
    if all_ok:
        print("🎉 모든 필수 설정이 올바르게 구성되었습니다.")
    else:
        print("🔥 하나 이상의 필수 설정에 문제가 있습니다. 위의 로그를 확인하고 수정해주세요.")
    print("-------------------------------------------------")

    return all_ok

if __name__ == "__main__":
    check_secrets()