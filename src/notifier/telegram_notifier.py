# -*- coding: utf-8 -*-
"""텔레그램 메시지 전송을 위한 비동기 유틸리티."""
import asyncio
import logging
import os
from aiogram import Bot
from aiogram.types import BotCommand
from dotenv import load_dotenv

# .env 파일에서 환경 변수 로드
load_dotenv()

# --- 환경 변수에서 텔레그램 설정 로드 ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 로거 설정
logger = logging.getLogger(__name__)

# --- 봇 인스턴스 ---
# 토큰이 설정된 경우에만 봇 인스턴스 생성
bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

async def send_telegram_message(message: str):
    """
    텔레그램으로 비동기 메시지를 전송합니다.
    봇 토큰이나 채팅 ID가 없으면 경고를 로깅하고 메시지를 보내지 않습니다.
    """
    if not bot or not TELEGRAM_CHAT_ID:
        logger.warning("텔레그램 봇 토큰 또는 채팅 ID가 설정되지 않았습니다. 메시지를 보낼 수 없습니다.")
        return

    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info("텔레그램 메시지를 성공적으로 전송했습니다.")
    except Exception as e:
        logger.error(f"텔레그램 메시지 전송 실패: {e}", exc_info=True)

async def send_backtest_results(stats_path: str, plot_path: str):
    """
    백테스트 결과(통계 및 시각화 파일 경로)를 텔레그램으로 전송합니다.
    """
    if not bot or not TELEGRAM_CHAT_ID:
        logger.warning("텔레그램 설정이 없어 백테스트 결과를 전송할 수 없습니다.")
        return

    try:
        message = (
            f"🚀 백테스트 완료!\n\n"
            f"📊 통계 파일:\n`{stats_path}`\n\n"
            f"📈 시각화 파일:\n`{plot_path}`"
        )
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, 
            text=message,
            parse_mode="Markdown"
        )
        logger.info("백테스트 결과 메시지를 텔레그램으로 전송했습니다.")
    except Exception as e:
        logger.error(f"백테스트 결과 전송 실패: {e}", exc_info=True)


async def send_daily_report(account_summary: dict):
    """
    일일 계좌 요약 리포트를 텔레그램으로 전송합니다.
    """
    if not bot or not TELEGRAM_CHAT_ID:
        logger.warning("텔레그램 설정이 없어 일일 리포트를 전송할 수 없습니다.")
        return

    try:
        # 숫자 포맷팅
        equity = f"${account_summary.get('total_equity', 0):,.2f}"
        available = f"${account_summary.get('available_balance', 0):,.2f}"
        pnl = account_summary.get('total_pnl', 0)
        pnl_str = f"${pnl:,.2f}"
        pnl_icon = "📈" if pnl >= 0 else "📉"

        # 포지션 정보 문자열 생성
        positions = account_summary.get('open_positions', [])
        if positions:
            pos_list = []
            for p in positions:
                side_icon = "🔼" if p['side'] == 'long' else "🔽"
                pos_list.append(
                    f"  {side_icon} {p['symbol']}: {p['size']} @ ${p['entryPrice']} (PNL: ${p['pnl']})"
                )
            positions_str = "\n".join(pos_list)
        else:
            positions_str = "  (없음)"

        message = (
            f"🔔 일일 계좌 리포트\n\n"
            f"💰 총 자산: {equity}\n"
            f"💵 사용 가능: {available}\n"
            f"{pnl_icon} 총 미실현손익: {pnl_str}\n\n"
            f"📊 현재 포지션:\n{positions_str}"
        )
        
        await send_telegram_message(message)
        logger.info("일일 계좌 리포트를 텔레그램으로 전송했습니다.")

    except Exception as e:
        logger.error(f"일일 리포트 전송 실패: {e}", exc_info=True)


async def set_bot_commands():
    """텔레그램 봇의 명령어 메뉴를 설정합니다."""
    if not bot:
        return
        
    commands = [
        BotCommand(command="/status", description="현재 봇의 상태를 확인합니다."),
        BotCommand(command="/report", description="최신 리포트를 요청합니다."),
        BotCommand(command="/stop", description="봇을 중지합니다 (관리자)."),
    ]
    try:
        await bot.set_my_commands(commands)
        logger.info("텔레그램 봇 명령어를 성공적으로 설정했습니다.")
    except Exception as e:
        logger.error(f"봇 명령어 설정 실패: {e}", exc_info=True)

async def main():
    """테스트를 위한 메인 함수."""
    logging.basicConfig(level=logging.INFO)
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("텔레그램 봇 토큰과 채팅 ID를 .env 파일에 설정해주세요.")
        return
        
    print("텔레그램 봇 명령어 설정 중...")
    await set_bot_commands()
    
    print("테스트 메시지 전송 중...")
    await send_telegram_message("안녕하세요! 텔레그램 봇이 시작되었습니다.")
    
    print("테스트 백테스트 결과 전송 중...")
    await send_backtest_results("outputs/backtests/BTCUSDT_20250601_20250901_MA_10_30_stats.txt", "outputs/backtests/BTCUSDT_20250601_20250901_MA_10_30_plot.html")

if __name__ == "__main__":
    # .env 파일이 프로젝트 루트에 있다고 가정
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    load_dotenv(dotenv_path=dotenv_path)
    
    asyncio.run(main())
