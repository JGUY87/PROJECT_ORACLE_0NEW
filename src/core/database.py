# -*- coding: utf-8 -*-
"""
데이터베이스 연결 및 세션 관리를 위한 SQLAlchemy 설정.

이 모듈은 SQLite 데이터베이스에 대한 엔진, 세션 로컬, 기본 모델 클래스를 제공합니다.
"""
import logging
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# --- 경로 및 URL 설정 ---
# 프로젝트 루트 디렉토리 (이 파일의 상위 2단계)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_FILE = "trading_bot.db"
DATABASE_URL = f"sqlite:///{PROJECT_ROOT / DATABASE_FILE}"

# --- SQLAlchemy 엔진 및 세션 설정 ---
# connect_args는 단일 스레드에서만 SQLite 연결을 사용하도록 보장하여 스레드 관련 문제를 방지합니다.
engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False},
    echo=False # SQL 쿼리 로깅 비활성화 (필요 시 True로 변경)
)

# 데이터베이스 세션 생성을 위한 SessionLocal 클래스
# autocommit=False, autoflush=False는 트랜잭션을 명시적으로 관리하기 위함입니다.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 모든 모델 클래스가 상속받아야 할 기본 클래스
Base = declarative_base()

# --- 데이터베이스 유틸리티 함수 ---
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 등에서 의존성 주입으로 사용될 데이터베이스 세션 제너레이터입니다.
    요청마다 세션을 생성하고, 요청이 끝나면 세션을 닫습니다.
    
    Yields:
        Session: SQLAlchemy 데이터베이스 세션 객체.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    데이터베이스를 초기화하고 Base를 상속하는 모든 모델에 대한 테이블을 생성합니다.
    
    주의: 이 함수를 호출하기 전에 관련된 모든 모델이 파이썬 환경에 임포트되어 있어야
    SQLAlchemy가 모델을 인식하고 테이블을 생성할 수 있습니다.
    """
    try:
        logging.info(f"데이터베이스를 초기화합니다. 경로: {DATABASE_URL}")
        # 모든 테이블 생성
        Base.metadata.create_all(bind=engine)
        logging.info("데이터베이스 초기화 및 테이블 생성이 완료되었습니다.")
    except Exception as e:
        logging.error(f"데이터베이스 초기화 중 오류 발생: {e}", exc_info=True)

# ======================= 사용 예시 =======================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("데이터베이스 초기화를 진행합니다...")
    init_db()
    print("\n`get_db` 함수를 사용하여 세션을 얻는 예시:")
    db_session_generator = get_db()
    my_session = next(db_session_generator)
    print(f"세션 객체: {my_session}")
    print(f"세션 활성 여부: {my_session.is_active}")
    my_session.close()
    print(f"세션 종료 후 활성 여부: {my_session.is_active}")