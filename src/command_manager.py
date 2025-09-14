# -*- coding: utf-8 -*-
"""
프로세스 간 통신(IPC)을 위한 명령어 관리 모듈.
파일 기반의 큐 시스템을 사용하여 Telegram 리스너와 거래 엔진 간의 통신을 중재합니다.

주요 기능:
- 명령어 전송: 리스너가 거래 엔진에 실행할 명령어를 보냅니다.
- 결과 대기 및 수신: 리스너가 보낸 명령어의 처리 결과를 비동기적으로 기다립니다.
- 명령어 수신 및 처리: 거래 엔진이 대기 중인 명령어를 가져와 처리합니다.
- 결과 반환: 거래 엔진이 명령어 처리 결과를 파일에 기록합니다.
- 파일 잠금을 통한 동시 접근 제어.
"""
import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from filelock import FileLock, Timeout

# --- 상수 정의 ---
COMMAND_DIR = Path("outputs/commands")
COMMAND_QUEUE_FILE = COMMAND_DIR / "command_queue.json"
RESULT_DIR = COMMAND_DIR / "results"
LOCK_TIMEOUT = 5  # 파일 잠금 대기 시간 (초)

# --- 디렉토리 초기화 ---
COMMAND_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# --- 로깅 설정 ---
logger = logging.getLogger(__name__)

# --- 리스너(클라이언트) 측 함수 ---

async def send_command(command: str, params: dict = None, timeout: int = 10) -> dict:
    """
    거래 엔진에 명령어를 보내고 결과가 올 때까지 대기합니다.

    Args:
        command (str): 실행할 명령어 이름 (예: 'get_balance').
        params (dict, optional): 명령어에 필요한 파라미터. Defaults to None.
        timeout (int, optional): 결과 파일을 기다리는 최대 시간 (초). Defaults to 10.

    Returns:
        dict: 명령어 처리 결과. 성공 또는 실패 정보를 포함합니다.
    """
    command_id = str(uuid.uuid4())
    logger.info(f"명령어 전송 시도: {command} (ID: {command_id})")

    queue_lock = FileLock(f"{COMMAND_QUEUE_FILE}.lock", timeout=LOCK_TIMEOUT)
    
    try:
        with queue_lock:
            try:
                with open(COMMAND_QUEUE_FILE, 'r', encoding='utf-8') as f:
                    queue = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                queue = []
            
            queue.append({
                "id": command_id,
                "command": command,
                "params": params or {},
                "timestamp": time.time()
            })

            with open(COMMAND_QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(queue, f, indent=4)
        
        logger.info(f"명령어 큐에 추가 완료: {command} (ID: {command_id})")
        return await await_result(command_id, timeout)

    except Timeout:
        logger.error("명령어 큐 파일 잠금 시간 초과.")
        return {"status": "error", "message": "명령어 큐에 접근할 수 없습니다 (Lock Timeout)."}
    except Exception as e:
        logger.error(f"명령어 전송 중 예외 발생: {e}", exc_info=True)
        return {"status": "error", "message": f"명령어 전송 중 오류 발생: {e}"}

async def await_result(command_id: str, timeout: int) -> dict:
    """
    지정된 command_id에 대한 결과 파일이 생성될 때까지 비동기적으로 대기합니다.
    """
    result_file = RESULT_DIR / f"result_{command_id}.json"
    start_time = time.time()
    
    logger.info(f"결과 대기 시작: {command_id} (최대 {timeout}초)")

    while time.time() - start_time < timeout:
        if result_file.exists():
            try:
                # 파일 읽기 시에도 잠재적 충돌 방지를 위해 잠금 사용
                result_lock = FileLock(f"{result_file}.lock", timeout=LOCK_TIMEOUT)
                with result_lock:
                    with open(result_file, 'r', encoding='utf-8') as f:
                        result = json.load(f)
                
                # 결과 파일을 읽은 후 삭제
                try:
                    result_file.unlink()
                    Path(f"{result_file}.lock").unlink(missing_ok=True)
                except OSError as e:
                    logger.warning(f"결과 파일 또는 잠금 파일 삭제 실패: {e}")

                logger.info(f"결과 수신 성공: {command_id}")
                return result

            except Timeout:
                logger.error(f"결과 파일 잠금 시간 초과: {command_id}")
                return {"status": "error", "message": "결과 파일을 읽는 데 실패했습니다 (Lock Timeout)."}
            except Exception as e:
                logger.error(f"결과 파일 읽기/삭제 중 오류: {e}", exc_info=True)
                return {"status": "error", "message": f"결과 처리 중 오류 발생: {e}"}
        
        await asyncio.sleep(0.2)  # 0.2초 간격으로 확인

    logger.warning(f"결과 대기 시간 초과: {command_id}")
    return {"status": "error", "message": "거래 엔진으로부터 응답이 없습니다 (Timeout)."}


# --- 거래 엔진(서버) 측 함수 ---

def get_command() -> dict | None:
    """
    명령어 큐에서 가장 오래된 명령어를 가져오고 큐에서 제거합니다.
    가져올 명령어가 없으면 None을 반환합니다.
    """
    queue_lock = FileLock(f"{COMMAND_QUEUE_FILE}.lock", timeout=LOCK_TIMEOUT)
    
    try:
        with queue_lock:
            try:
                with open(COMMAND_QUEUE_FILE, 'r', encoding='utf-8') as f:
                    queue = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return None

            if not queue:
                return None

            # 가장 오래된 명령어 (첫 번째 항목) 가져오기
            command_to_process = queue.pop(0)
            
            # 큐 업데이트
            with open(COMMAND_QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(queue, f, indent=4)
            
            logger.info(f"명령어 수신 및 처리 시작: {command_to_process['command']} (ID: {command_to_process['id']})")
            return command_to_process

    except Timeout:
        logger.warning("명령어 큐 파일 잠금을 얻지 못했습니다 (get_command).")
        return None
    except Exception as e:
        logger.error(f"명령어 수신 중 예외 발생: {e}", exc_info=True)
        return None

def write_result(command_id: str, result: dict):
    """
    명령어 처리 결과를 파일에 기록합니다.
    """
    result_file = RESULT_DIR / f"result_{command_id}.json"
    result_lock = FileLock(f"{result_file}.lock", timeout=LOCK_TIMEOUT)
    
    try:
        with result_lock:
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=4)
        logger.info(f"결과 기록 완료: {command_id}")
    except Timeout:
        logger.error(f"결과 파일 잠금 시간 초과 (write_result): {command_id}")
    except Exception as e:
        logger.error(f"결과 기록 중 예외 발생: {e}", exc_info=True)
