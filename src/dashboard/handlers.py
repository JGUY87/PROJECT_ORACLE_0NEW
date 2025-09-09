# -*- coding: utf-8 -*-
"""
텔레그램 봇 명령어 핸들러
"""
import asyncio
import os # Added for /report
import glob # Added for /report

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile

from ..engine.manager import TradingEngine
from ..core import order_helpers
from ..core.exchange_info import get_balance

# 라우터 객체 생성
router = Router(name="main_router")

# TradingEngine의 싱글턴 인스턴스 가져오기
engine = TradingEngine()

@router.message(Command("status"))
async def handle_status(message: Message):
    """봇의 현재 상태를 반환합니다."""
    status = engine.get_status()
    await message.reply(f"✅ 엔진 상태:\n" 
                        f"- 실행 여부: {status['is_running']}\n" 
                        f"- 현재 전략: {status['strategy']}\n" 
                        f"- 현재 심볼: {status['symbol']}")

@router.message(Command("run"))
async def handle_run(message: Message):
    """트레이딩 엔진을 시작합니다."""
    args = message.text.split()
    if len(args) < 3:
        await message.reply("❌ 사용법: /run [전략명] [심볼]")
        return
    
    strategy = args[1]
    symbol = args[2]
    response = engine.start(strategy, symbol)
    await message.reply(f"✅ {response}")

@router.message(Command("stop"))
async def handle_stop(message: Message):
    """트레이딩 엔진을 중지합니다."""
    response = engine.stop()
    await message.reply(f"🛑 {response}")

@router.message(Command("buy"))
async def handle_buy(message: Message):
    """시장가 매수 주문을 실행합니다."""
    args = message.text.split()
    if len(args) < 3:
        await message.reply("❌ 사용법: /buy [심볼] [수량]")
        return
    
    try:
        symbol = args[1]
        qty = float(args[2])
        result = await order_helpers.place_market_order(symbol, 'buy', qty)
        await message.reply(f"✅ 매수 주문 성공:\n{result}")
    except Exception as e:
        await message.reply(f"❌ 매수 주문 실패: {e}")

@router.message(Command("sell"))
async def handle_sell(message: Message):
    """시장가 매도 주문을 실행합니다."""
    args = message.text.split()
    if len(args) < 3:
        await message.reply("❌ 사용법: /sell [심볼] [수량]")
        return
    
    try:
        symbol = args[1]
        qty = float(args[2])
        result = await order_helpers.place_market_order(symbol, 'sell', qty)
        await message.reply(f"✅ 매도 주문 성공:\n{result}")
    except Exception as e:
        await message.reply(f"❌ 매도 주문 실패: {e}")

@router.message(Command("restart"))
async def handle_restart(message: Message):
    """트레이딩 엔진을 재시작합니다."""
    response = engine.restart()
    await message.reply(f"♻️ {response}")

@router.message(Command("close"))
async def handle_close(message: Message):
    """포지션을 종료합니다."""
    args = message.text.split()
    if len(args) < 4:
        await message.reply("❌ 사용법: /close [심볼] [수량] [포지션 사이드 long/short]")
        return
    
    try:
        symbol = args[1]
        qty = float(args[2])
        position_side = args[3].lower()
        if position_side not in ['long', 'short']:
            raise ValueError("Position side must be 'long' or 'short'")

        result = await order_helpers.close_position(symbol, position_side, qty)
        await message.reply(f"✅ 포지션 종료 주문 성공:\n{result}")
    except Exception as e:
        await message.reply(f"❌ 포지션 종료 주문 실패: {e}")

@router.message(Command("switch_strategy"))
async def handle_switch_strategy(message: Message):
    """실행 중인 전략을 변경합니다."""
    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ 사용법: /switch_strategy [전략명]")
        return
    
    new_strategy = args[1]
    response = engine.switch_strategy(new_strategy)
    await message.reply(f"🔄 {response}")

@router.message(Command("tp"))
async def handle_tp(message: Message):
    """익절(Take Profit)을 설정합니다."""
    args = message.text.split()
    if len(args) < 3:
        await message.reply("❌ 사용법: /tp [심볼] [익절가격]")
        return
    
    try:
        symbol = args[1]
        tp_price = float(args[2])
        result = await order_helpers.set_take_profit_stop_loss(symbol, tp_price=tp_price)
        await message.reply(f"✅ TP 설정 요청: {result.get('message', 'No message')}")
    except Exception as e:
        await message.reply(f"❌ TP 설정 실패: {e}")

@router.message(Command("sl"))
async def handle_sl(message: Message):
    """손절(Stop Loss)을 설정합니다."""
    args = message.text.split()
    if len(args) < 3:
        await message.reply("❌ 사용법: /sl [심볼] [손절가격]")
        return
    
    try:
        symbol = args[1]
        sl_price = float(args[2])
        result = await order_helpers.set_take_profit_stop_loss(symbol, sl_price=sl_price)
        await message.reply(f"✅ SL 설정 요청: {result.get('message', 'No message')}")
    except Exception as e:
        await message.reply(f"❌ SL 설정 실패: {e}")

@router.message(Command("help"))
async def handle_help(message: Message):
    """도움말 메시지를 보여줍니다."""
    help_text = """
    명령어 도움말
    
    상태 및 정보:
    /status - 봇의 현재 실행 상태를 봅니다.
    /summary - 봇의 상태를 요약하여 봅니다.
    /balance - 거래소 잔고를 조회합니다.
    /report - 최신 백테스트 리포트를 요청합니다.
    
    엔진 제어:
    /run [전략] [심볼] - 특정 전략과 심볼로 봇을 시작합니다.
    /stop - 봇을 중지합니다.
    /restart - 마지막 설정으로 봇을 재시작합니다.
    /switch_strategy [전략] - 실행 중인 전략을 변경합니다.
    
    주문 관리:
    /buy [심볼] [수량] - 시장가 매수 주문
    /sell [심볼] [수량] - 시장가 매도 주문
    /close [심볼] [수량] [side] - 포지션 종료
    /tp [심볼] [가격] - 익절 설정 (구현 중)
    /sl [심볼] [가격] - 손절 설정 (구현 중)
    """
    await message.reply(help_text)

@router.message(Command("summary"))
async def handle_summary(message: Message):
    """봇의 상태를 요약하여 보여줍니다."""
    # For now, it's an alias for /status. Can be expanded later.
    await handle_status(message)

@router.message(Command("balance"))
async def handle_balance(message: Message):
    """거래소 잔고를 조회합니다."""
    try:
        # USDT 잔고 조회 (기본값)
        balance_info = await get_balance('USDT')
        
        if balance_info:
            total = balance_info.get('total', 0)
            free = balance_info.get('free', 0)
            used = balance_info.get('used', 0)
            
            response_text = (
                f"💰 **USDT 잔고 조회**\n" 
                f"- 총액: `{total:.4f}` USDT\n" 
                f"- 사용 가능: `{free:.4f}` USDT\n" 
                f"- 사용 중: `{used:.4f}` USDT"
            )
        else:
            response_text = "❌ USDT 잔고 정보를 가져올 수 없습니다. API 키/시크릿 또는 네트워크 상태를 확인해주세요."
            
        await message.reply(response_text, parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ 잔고 조회 중 오류 발생: {e}")

@router.message(Command("report"))
async def handle_report(message: Message):
    """최신 백테스트 리포트를 전송합니다."""
    try:
        # outputs/backtests 디렉토리에서 최신 HTML 리포트 파일 찾기
        report_files = glob.glob("outputs/backtests/*.html")
        if not report_files:
            await message.reply("❌ 생성된 백테스트 리포트가 없습니다. 먼저 /run_backtest 명령어를 사용해주세요.")
            return

        # 가장 최근에 수정된 파일 찾기
        latest_report = max(report_files, key=os.path.getmtime)
        
        # 파일 전송
        document = FSInputFile(latest_report)
        await message.answer_document(document, caption="📈 최신 백테스트 리포트입니다.")
        
    except Exception as e:
        await message.reply(f"❌ 리포트 전송 중 오류 발생: {e}")

@router.message(Command("run_backtest"))
async def handle_run_backtest(message: Message):
    """백테스트를 실행하고 결과를 즉시 전송합니다."""
    args = message.text.split()
    if len(args) < 3:
        await message.reply("❌ 사용법: /run_backtest [심볼] [시작일 YYYY-MM-DD] [단기MA] [장기MA]")
        await message.reply("예시: /run_backtest BTCUSDT 2023-01-01 10 30") # Corrected symbol format
        return
    
    try:
        symbol = args[1].replace('/', '') # Allow both BTC/USDT and BTCUSDT
        start_date = args[2]
        fast_ma = int(args[3]) if len(args) > 3 else 10
        slow_ma = int(args[4]) if len(args) > 4 else 30

        await message.reply(f"📈 백테스트를 시작합니다: {symbol} ({start_date}부터, MA {fast_ma}/{slow_ma}). 잠시만 기다려주세요...")
        
        # Corrected and simplified command
        command = f"python run_backtest.py --symbol {symbol} --start_date {start_date} --fast_ma {fast_ma} --slow_ma {slow_ma}"
        
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            # The script now prints the filename to stdout
            stats_filename = stdout.decode().strip()
            if os.path.exists(stats_filename):
                document = FSInputFile(stats_filename)
                await message.answer_document(document, caption=f"✅ 백테스트 완료: {os.path.basename(stats_filename)}")
            else:
                await message.reply(f"❌ 백테스트는 성공했지만 결과 파일을 찾을 수 없습니다: {stats_filename}")
        else:
            # Send stderr if there was an error
            error_message = stderr.decode().strip()
            await message.reply(f"❌ 백테스트 실행 중 오류 발생:\n```\n{error_message}\n```")
            
    except Exception as e:
        await message.reply(f"❌ 백테스트 처리 중 오류 발생: {e}")


@router.message(Command("train_ppo"))
async def handle_train_ppo(message: Message):
    """PPO 모델 학습을 시작합니다."""
    await message.reply("📈 PPO 모델 학습을 시작합니다. 잠시만 기다려주세요...")
    try:
        # PPO 학습 시작 (플레이스홀더)
        result = engine.train_ppo_model()
        await message.reply(f"✅ PPO 학습 완료: {result.get('note', 'No details')}")
    except Exception as e:
        await message.reply(f"❌ PPO 학습 중 오류 발생: {e}")
