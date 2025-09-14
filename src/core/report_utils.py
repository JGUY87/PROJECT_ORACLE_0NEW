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
from datetime import datetime, timezone, timedelta

# Define KST for consistent timestamps
KST = timezone(timedelta(hours=9))

# This ensures the outputs directory exists.
# This navigates up from src/core/ to the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# ============================================================ 
# ⚙️ [E] 엔진 상태 기록 함수
# ============================================================ 
def write_engine_status(status: str, message: str, timestamp: str, top_symbols: Optional[List[str]] = None):
    """Records the current state of the engine to a JSON file."""
    status_path = os.path.join(OUTPUTS_DIR, "engine_status.json")
    status_data = {
        "status": status,
        "message": message,
        "last_update_kst": timestamp,
        "top_symbols": top_symbols or []
    }
    try:
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        # Using print is safer here to avoid recursive logging errors.
        print(f"CRITICAL: Failed to write engine status: {e}")

# ============================================================ 
# 🚨 [D] 에러 로그 기록 함수 (Loguru가 자동으로 처리)
# ============================================================ 
def log_error(message: str, exc_info=False):
    """
    DEPRECATED: Logs a message to the error log file.
    It is recommended to use logger.exception() from Loguru directly
    for better context and automatic traceback capturing.
    """
    # This function is kept for backward compatibility but should be phased out.
    # For now, it just prints to stderr.
    print(f"ERROR (from deprecated log_error): {message}", file=sys.stderr)

# ============================================================ 
# 📆 [F] 일일 요약 리포트 기록
# ============================================================ 
def generate_daily_report():
    """Generates a daily report summarizing the day's trades."""
    # This feature is not currently implemented.
    report_path = os.path.join(OUTPUTS_DIR, "daily_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"## Daily Report ({datetime.now(KST).strftime('%Y-%m-%d')}) ##\n\n")
        f.write("No trades recorded today.\n")
    return report_path
