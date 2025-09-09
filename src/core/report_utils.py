# core/report_utils.py
"""
📋 LIBRA 리포트/로그/상태 기록 유틸리티 (Loguru 기반)
- 실전/백테스트 공통 지원
- 에러/상태/거래로그/리포트 자동 저장
- 폴더 자동 생성, 예외내성 강화, 한글 주석 포함
"""

import os
import json
import sys
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

# 🔧 .env 환경 변수 로드
load_dotenv()

# 📂 경로 설정 (.env에 없으면 기본값 사용)
LOG_DIR = os.getenv("LOG_DIR", "outputs/live_logs")
REPORT_DIR = os.getenv("REPORT_DIR", "outputs/live_reports")
ERROR_LOG_FILE = os.getenv("ERROR_LOG_FILE", "outputs/error_log.log") # .log 확장자 사용
DAILY_REPORT_FILE = os.getenv("DAILY_REPORT_FILE", "outputs/daily_report.txt")
ENGINE_STATUS_FILE = os.getenv("ENGINE_STATUS_FILE", "outputs/engine_status.json")
INFO_LOG_FILE = os.getenv("INFO_LOG_FILE", "outputs/info.log")

# ✅ Loguru 로거 설정
logger.remove() # 기본 핸들러 제거
logger.add(sys.stderr, level="DEBUG") # 콘솔 출력
logger.add(INFO_LOG_FILE, level="INFO", rotation="10 MB", compression="zip", encoding="utf-8") # 정보 로그 파일
logger.add(ERROR_LOG_FILE, level="ERROR", rotation="10 MB", compression="zip", encoding="utf-8") # 에러 로그 파일

# ============================================================ 
# 📁 [A] 경로 자동 생성 유틸
# ============================================================ 
def ensure_dir_exists(path: str):
    """
    📁 폴더가 없으면 자동 생성
    """
    try:
        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
    except Exception as e:
        logger.error(f"[경로 생성 실패] {path} / {e}")

# ============================================================ 
# 📝 [B] 로그 저장 함수 (거래내역 포함)
# ============================================================ 
def save_log(data, output_dir=LOG_DIR, filename="trade_log.csv"):
    """
    🧾 거래 로그 저장 (DataFrame, dict, list 모두 지원)
    """
    try:
        ensure_dir_exists(output_dir)
        path = os.path.join(output_dir, filename)

        if isinstance(data, dict):
            df = pd.DataFrame([data])
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, pd.DataFrame):
            df = data
        else:
            raise ValueError("지원되지 않는 데이터 형식")

        df.to_csv(path, index=False, encoding="utf-8")
        logger.info(f"[✅] 거래 로그 저장 완료: {path}")
    except Exception as e:
        logger.error(f"[거래 로그 저장 오류] {e}")

# ============================================================ 
# 📑 [C] 리포트 저장 함수
# ============================================================ 
def save_report(data, output_dir=REPORT_DIR, filename="auto_report.csv"):
    """
    📋 리포트 저장 (DataFrame, dict, list 모두 지원)
    """
    try:
        ensure_dir_exists(output_dir)
        path = os.path.join(output_dir, filename)

        if isinstance(data, dict):
            df = pd.DataFrame([data])
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, pd.DataFrame):
            df = data
        else:
            raise ValueError("지원되지 않는 데이터 형식")

        df.to_csv(path, index=False, encoding="utf-8")
        logger.info(f"[✅] 리포트 저장 완료: {path}")
    except Exception as e:
        logger.error(f"[리포트 저장 오류] {e}")

# ============================================================ 
# 🚨 [D] 에러 로그 기록 함수 (Loguru가 자동으로 처리)
# ============================================================ 
def log_error(msg: str):
    """
    🚨 에러 로그 기록 (Loguru가 파일에 자동으로 기록)
    """
    logger.error(msg)

# ============================================================ 
# ⚙️ [E] 엔진 상태 기록 함수
# ============================================================ 
def write_engine_status(status: dict):
    """
    ⚙️ 엔진 상태(json) 기록 (outputs/engine_status.json)
    """
    try:
        ensure_dir_exists(os.path.dirname(ENGINE_STATUS_FILE))
        with open(ENGINE_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
        logger.info(f"[✅] 엔진 상태 기록 완료: {ENGINE_STATUS_FILE}")
    except Exception as e:
        logger.error(f"[엔진 상태 기록 실패] {e}")

# ============================================================ 
# 📆 [F] 일일 요약 리포트 기록
# ============================================================ 
def generate_daily_report(status: dict):
    """
    📆 일일 리포트 기록 (outputs/daily_report.txt)
    """
    try:
        ensure_dir_exists(os.path.dirname(DAILY_REPORT_FILE))
        with open(DAILY_REPORT_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {json.dumps(status, ensure_ascii=False)}\n")
        logger.info(f"[✅] 일일 리포트 기록 완료: {DAILY_REPORT_FILE}")
    except Exception as e:
        logger.error(f"[일일 리포트 저장 실패] {e}")

# ============================================================ 
# 🧪 [G] 테스트 실행 (직접 실행 시)
# ============================================================ 
if __name__ == "__main__":
    logger.info("로깅 시스템 테스트 시작...")
    
    # 엔진 상태 예시 저장
    write_engine_status({"timestamp": datetime.now().isoformat(), "status": "테스트"})

    # 일일 리포트 예시 저장
    generate_daily_report({"전략": "흑우냠냠", "수익률": 12.3, "상태": "정상"})

    # 리포트 저장 예시
    save_report([{"date": "2025-08-09", "profit": 12.3}], filename="example_report.csv")

    # 거래 로그 저장 예시
    save_log([{"timestamp": "2025-08-09 12:00", "side": "buy", "price": 42800, "amount": 0.01}], filename="example_trade_log.csv")
    
    # 에러 로그 테스트
    log_error("이것은 테스트 에러 메시지입니다.")
    logger.info("로깅 시스템 테스트 완료.")
