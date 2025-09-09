# -*- coding: utf-8 -*-
"""
데이터베이스 및 테이블 생성 스크립트
"""
import logging
from src.core.database import init_db

# 로깅 설정
logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    logging.info("Initializing database...")
    try:
        init_db()
        logging.info("Database initialization successful. 'trading_bot.db' is ready.")
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")
