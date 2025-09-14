# -*- coding: utf-8 -*-
"""
애플리케이션 메인 진입점
"""
import asyncio
import logging
from dotenv import load_dotenv
from .config.utils import get_telegram_info # get_telegram_info 함수 임포트
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from .dashboard.handlers import router as main_router

async def main():
    """
    봇을 설정하고 시작합니다.
    """
    load_dotenv() # .env 파일에서 환경 변수 로드
    # 기본 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )

    # 설정 유틸리티를 통해 텔레그램 정보 가져오기
    token, _ = get_telegram_info()
    if not token:
        logging.error("텔레그램 봇 토큰을 찾을 수 없습니다. (.env 또는 accounts.json) 봇을 시작할 수 없습니다.")
        return

    # 봇과 디스패처 인스턴스 생성
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher()

    # 핸들러 라우터 포함
    dp.include_router(main_router)

    logging.info("봇이 시작됩니다...")
    # 봇 폴링 시작 (봇의 모든 업데이트 수신 대기)
    logging.info("Bot polling started...")
    await dp.start_polling(bot)
    logging.info("Bot polling stopped.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("봇이 수동으로 중지되었습니다.")