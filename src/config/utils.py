# -*- coding: utf-8 -*-
"""민감 정보 로드 및 키 관리를 위한 유틸리티 함수들."""
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv

def _abs_path(rel_path: str) -> Path:
    """이 파일의 상대 경로로부터 절대 경로를 반환합니다."""
    return Path(os.path.abspath(os.path.join(os.path.dirname(__file__), rel_path)))

def _load_json_file(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    JSON 파일을 안전하게 로드하고, 내용과 에러 메시지를 반환합니다.

    Args:
        path (Path): JSON 파일의 경로.

    Returns:
        Tuple[Optional[Dict[str, Any]], Optional[str]]: 로드된 데이터와 에러 메시지 (성공 시 None).
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, f"❗️ [에러] 파일을 찾을 수 없습니다: {path}"
    except json.JSONDecodeError:
        return None, f"❗️ [에러] JSON 파싱 실패: {path}"
    except Exception as e:
        return None, f"❗️ [에러] {path}를 읽는 중 예기치 않은 오류 발생: {e}"

def get_account(exchange: str = "bybit", idx: int = 0, accounts_path: Optional[Path] = None, on_error=None) -> Dict[str, Any]:
    """
    accounts.json에서 특정 거래소 계정 설정을 가져옵니다.

    Args:
        exchange (str): 거래소 이름 (예: 'binance', 'bybit').
        idx (int): 한 거래소에 여러 계정이 있을 경우의 인덱스.
        accounts_path (Optional[Path]): accounts.json 파일의 절대 경로.
        on_error (callable): 에러 발생 시 실행할 콜백 함수.

    Returns:
        Dict[str, Any]: 계정 정보 딕셔너리.
    """
    if accounts_path is None:
        accounts_path = _abs_path("../../configs/accounts.json")

    data, error = _load_json_file(accounts_path)

    if error:
        print(error)
        if on_error:
            on_error(error)
        return {}

    if not data:
        return {}

    # 단일 계정 객체와 계정 리스트 모두 처리
    accounts = data if isinstance(data, list) else [data]

    # 거래소 이름과 일치하는 계정 필터링
    matching_accounts = [acc for acc in accounts if exchange.lower() in acc.get("name", "").lower()]

    if matching_accounts:
        if idx < len(matching_accounts):
            return matching_accounts[idx]
        return matching_accounts[0] # 일치하는 첫 번째 계정으로 대체

    # 이름이 일치하지 않으면 인덱스로 대체
    if idx < len(accounts):
        return accounts[idx]

    return {}

def get_api_keys(exchange: str = "bybit", idx: int = 0, dotenv_path: Optional[Path] = None, accounts_path: Optional[Path] = None, on_error=None) -> Tuple[str, str]:
    """
    주어진 거래소의 API 키와 시크릿을 반환하며, 환경 변수를 우선으로 합니다.

    Args:
        exchange (str): 거래소 이름.
        idx (int): 계정 인덱스.
        dotenv_path (Optional[Path]): .env 파일 경로.
        accounts_path (Optional[Path]): accounts.json 파일 경로.
        on_error (callable): 에러 발생 시 콜백.

    Returns:
        Tuple[str, str]: API 키와 시크릿.
    """
    if dotenv_path:
        load_dotenv(dotenv_path)

    key_env = os.getenv(f"{exchange.upper()}_API_KEY", "")
    sec_env = os.getenv(f"{exchange.upper()}_API_SECRET", "")

    if key_env and sec_env:
        return key_env, sec_env

    account = get_account(exchange, idx, accounts_path, on_error)
    api_key = account.get("api_key") or account.get(f"{exchange}_api_key", "")
    api_secret = account.get("api_secret") or account.get(f"{exchange}_api_secret", "")

    return api_key, api_secret

def get_telegram_info(idx: int = 0, dotenv_path: Optional[Path] = None, accounts_path: Optional[Path] = None, on_error=None) -> Tuple[str, str]:
    """
    텔레그램 봇 토큰과 채팅 ID를 반환하며, 환경 변수를 우선으로 합니다.

    Args:
        idx (int): 계정 인덱스.
        dotenv_path (Optional[Path]): .env 파일 경로.
        accounts_path (Optional[Path]): accounts.json 파일 경로.
        on_error (callable): 에러 발생 시 콜백.

    Returns:
        Tuple[str, str]: 텔레그램 토큰과 채팅 ID.
    """
    if dotenv_path:
        load_dotenv(dotenv_path)

    token_env = os.getenv("TELEGRAM_TOKEN", "")
    chatid_env = os.getenv("TELEGRAM_CHAT_ID", "")

    if token_env and chatid_env:
        return token_env, chatid_env

    # accounts.json에서 텔레그램 정보는 특정 거래소에 묶여있지 않을 수 있음
    account = get_account(exchange="telegram", idx=idx, accounts_path=accounts_path, on_error=on_error)
    if not account: # 구버전 구조를 위한 대체 처리
        account = get_account(idx=idx, accounts_path=accounts_path, on_error=on_error)

    return account.get("telegram_token", ""), account.get("telegram_chat_id", "")

def get_upbit_keys(idx=0, dotenv_path=None, accounts_path=None, on_error=None):
    """업비트 키를 위한 편의 함수."""
    return get_api_keys("upbit", idx, dotenv_path, accounts_path, on_error)

def get_binance_keys(idx=0, dotenv_path=None, accounts_path=None, on_error=None):
    """바이낸스 키를 위한 편의 함수."""
    return get_api_keys("binance", idx, dotenv_path, accounts_path, on_error)

# 초기 임포트 시 프로젝트 루트의 .env 파일 로드
load_dotenv(_abs_path("../../.env"))

# ======================= 사용 예시 =======================
if __name__ == "__main__":
    print("BYBIT 키:", get_api_keys("bybit"))
    print("업비트 키:", get_upbit_keys())
    print("바이낸스 키:", get_binance_keys())
    print("텔레그램 정보:", get_telegram_info())
