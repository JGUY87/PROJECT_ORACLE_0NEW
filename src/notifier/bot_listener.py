import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# --- Imports ---
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.markdown import hcode
from dotenv import load_dotenv
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command

from src import command_manager as cm

# --- 기본 설정 ---
# .env 파일 로드 (프로젝트 루트에 있다고 가정)
dotenv_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=dotenv_path)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

# --- 환경 변수 및 상수 ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STATUS_FILE_PATH = Path("outputs/engine_status.json")
DAILY_REPORT_FILE = Path("outputs/daily_report.txt")
LOG_FILE_PATH = Path("outputs/info.log")
ERROR_LOG_FILE_PATH = Path("outputs/error_log.log")
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# --- 봇 및 디스패처 초기화 ---
if not TELEGRAM_BOT_TOKEN:
    logging.error("TELEGRAM_BOT_TOKEN이 .env 파일에 설정되지 않았습니다. 리스너를 시작할 수 없습니다.")
    sys.exit(1)

bot = Bot(token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
# FSM을 위한 스토리지 추가
dp = Dispatcher(storage=MemoryStorage())


# --- FSM 상태 정의 ---
class OrderForm(StatesGroup):
    side = State()      # 'buy' 또는 'sell'
    symbol = State()    # 예: BTCUSDT
    amount = State()    # 주문 수량

class TPSLForm(StatesGroup):
    side = State()      # 'tp' or 'sl'
    symbol = State()
    price = State()
    amount = State()

class StrategyForm(StatesGroup):
    strategy_name = State()
    model_path = State()

# --- IPC 명령어 처리 헬퍼 ---
async def send_engine_command(message: types.Message, command: str, params: dict = None, timeout: int = 20):
    """
    거래 엔진에 명령어를 전송하고 결과를 처리하여 사용자에게 응답합니다.
    """
    await message.answer(f"명령 실행 중: {command}")
    
    try:
        command_id = cm.send_command(command, params or {})
        
        # 사용자에게 대기 중임을 알림
        await message.edit_text(
            f"⏳ {hcode(command)} 명령을 엔진에 전송했습니다. 잠시만 기다려주세요...",
        )

        result = await cm.await_result(command_id, timeout)

        response_text = ""
        if result:
            status = result.get("status", "error")
            message_text = result.get("message", "결과 메시지가 없습니다.")
            data = result.get("data")

            if status == "success":
                response_text = f"✅ <b>명령 성공: {command}</b>\n\n{message_text}"
                if data:
                    formatted_data = json.dumps(data, indent=2, ensure_ascii=False)
                    escaped_data = formatted_data.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    response_text += f"\n\n<b>결과:</b>\n<pre>{escaped_data}</pre>"
            elif status == "info":
                response_text = f"ℹ️ <b>정보: {command}</b>\n\n{message_text}"
            else: # status == "error"
                response_text = f"❌ <b>명령 실패: {command}</b>\n\n{message_text}"
        else: # Timeout
            response_text = f"⌛️ <b>타임아웃: {command}</b>\n\n엔진이 시간 내에 응답하지 않았습니다. 엔진 상태를 확인해주세요."

        await message.edit_text(
            response_text,
            reply_markup=get_back_to_main_menu_keyboard(),
        )

    except Exception as e:
        logging.error(f"'{command}' 명령어 처리 중 예외 발생: {e}", exc_info=True)
        await message.edit_text(
            f"💥 <b>시스템 오류</b>\n\n{hcode(command)} 명령 처리 중 내부 오류가 발생했습니다.",
            reply_markup=get_back_to_main_menu_keyboard(),
        )


# --- 핵심 로직 함수 (메시지 생성) ---

async def get_status_message():
    """봇의 현재 상태 메시지를 생성합니다."""
    if not STATUS_FILE_PATH.exists():
        return "⚠️ 상태 파일을 찾을 수 없습니다."
    try:
        with open(STATUS_FILE_PATH, 'r', encoding='utf-8') as f:
            status_data = json.load(f)
        return (
            f"🤖 **거래 봇 현재 상태**\n\n"
            f"🕒 **마지막 업데이트:** `{status_data.get('last_update_kst', 'N/A')}`\n"
            f"⚙️ **현재 모드:** `{status_data.get('mode', 'N/A')}`\n"
            f"▶️ **마지막 활동:** `{status_data.get('last_action', 'N/A')}`\n"
            f"ℹ️ **추가 정보:** `{status_data.get('info', 'N/A')}`"
        )
    except Exception as e:
        logging.error(f"상태 메시지 생성 중 오류: {e}", exc_info=True)
        return "상태를 처리하는 중 오류가 발생했습니다."

async def get_file_content_message(file_path: Path, title: str, lines_to_show: int = 20):
    """파일의 마지막 N줄을 읽어 메시지를 생성합니다."""
    if not file_path.exists():
        return f"⚠️ {title} 파일을 찾을 수 없습니다."
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            content = "".join(lines[-lines_to_show:])
        if not content.strip():
            return f"⚠️ {title} 파일이 비어있습니다."
        return f"📄 **{title} (마지막 {lines_to_show}줄)**\n\n```\n{content}\n```"
    except Exception as e:
        logging.error(f"{title} 처리 중 오류: {e}", exc_info=True)
        return f"{title} 처리 중 오류가 발생했습니다."

# --- 키보드 생성 함수 ---

def get_main_menu_keyboard():
    """메인 메뉴 인라인 키보드를 생성합니다."""
    buttons = [
        [InlineKeyboardButton(text="📊 상태 및 정보", callback_data="menu_info")],
        [InlineKeyboardButton(text="⚙️ 엔진 제어", callback_data="menu_engine_control")],
        [InlineKeyboardButton(text="🛒 주문 관리", callback_data="menu_order_management")],
        [InlineKeyboardButton(text="🙋 도움말 새로고침", callback_data="show_help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_info_menu_keyboard():
    """'상태 및 정보' 메뉴 키보드를 생성합니다."""
    buttons = [
        [
            InlineKeyboardButton(text="🤖 상태", callback_data="show_status"),
            InlineKeyboardButton(text="📝 요약", callback_data="show_summary"),
            InlineKeyboardButton(text="💰 잔고", callback_data="show_balance")
        ],
        [
            InlineKeyboardButton(text="📈 보고서", callback_data="show_report"),
            InlineKeyboardButton(text="📜 로그", callback_data="show_logs"),
            InlineKeyboardButton(text="🚨 오류로그", callback_data="show_errorlog")
        ],
        [
            InlineKeyboardButton(text="⚙️ 전략정보", callback_data="show_config"),
            InlineKeyboardButton(text="뒤로가기", callback_data="show_help")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_engine_control_menu_keyboard():
    """'엔진 제어' 메뉴 키보드를 생성합니다."""
    buttons = [
        [
            InlineKeyboardButton(text="▶️ 시작", callback_data="engine_run"),
            InlineKeyboardButton(text="⏹️ 중지", callback_data="engine_stop"),
            InlineKeyboardButton(text="🔄 재시작", callback_data="engine_restart")
        ],
        [
            InlineKeyboardButton(text="🔀 전략변경", callback_data="engine_switch_strategy"),
            InlineKeyboardButton(text="▶️ 재개", callback_data="engine_resume")
        ],
        [
            InlineKeyboardButton(text="뒤로가기", callback_data="show_help")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_order_management_menu_keyboard():
    """'주문 관리' 메뉴 키보드를 생성합니다."""
    buttons = [
        [
            InlineKeyboardButton(text="🟢 매수", callback_data="order_buy"),
            InlineKeyboardButton(text="🔴 매도", callback_data="order_sell"),
            InlineKeyboardButton(text="🟡 포지션종료", callback_data="order_close")
        ],
        [
            InlineKeyboardButton(text="🎯 익절(TP)", callback_data="order_tp"),
            InlineKeyboardButton(text="🛡️ 손절(SL)", callback_data="order_sl")
        ],
        [
            InlineKeyboardButton(text="뒤로가기", callback_data="show_help")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_to_main_menu_keyboard():
    """'메인 메뉴로 돌아가기' 버튼만 있는 키보드를 생성합니다."""
    buttons = [
        [InlineKeyboardButton(text="« 메인 메뉴로 돌아가기", callback_data="show_help")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_help_text():
    """메인 도움말 텍스트를 반환합니다."""
    return "🙋 **명령어 안내**\n\n아래 메뉴에서 원하는 기능을 선택하세요."

# --- 메시지 핸들러 (최상위 명령어) ---

@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    """/start 명령어 처리"""
    await message.reply(
        "안녕하세요! 거래 봇 리스너가 활성화되었습니다.\n/help 명령어로 사용 가능한 모든 명령어를 확인하세요."
    )

@dp.message(F.text.startswith(("/help", "/menu")))
async def command_help_handler(message: types.Message):
    """/help 또는 /menu 명령어 처리"""
    await message.reply(get_help_text(), reply_markup=get_main_menu_keyboard())

# --- FSM 취소 핸들러 ---
@dp.message(Command('cancel'))
@dp.message(F.text.casefold() == 'cancel')
async def cancel_handler(message: types.Message, state: FSMContext):
    """모든 상태에서 대화 취소"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(
            "현재 진행 중인 작업이 없습니다.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    logging.info(f"Cancelling state {current_state} for user {message.from_user.id}")
    await state.clear()
    await message.answer(
        "진행 중이던 모든 작업을 취소했습니다.",
        reply_markup=get_main_menu_keyboard(),
    )

# --- 콜백 쿼리 핸들러 (메뉴 네비게이션) ---

@dp.callback_query(F.data == 'show_help')
async def cq_show_main_menu(callback_query: types.CallbackQuery, state: FSMContext):
    """메인 메뉴 표시"""
    await state.clear() # 메인 메뉴로 돌아갈 때 상태 초기화
    await callback_query.message.edit_text(
        get_help_text(),
        reply_markup=get_main_menu_keyboard(),
    )
    await callback_query.answer()

@dp.callback_query(F.data == 'menu_info')
async def cq_show_info_menu(callback_query: types.CallbackQuery):
    """'상태 및 정보' 메뉴 표시"""
    await callback_query.message.edit_text(
        "📊 **상태 및 정보**\n\n원하는 정보 버튼을 클릭하세요.",
        reply_markup=get_info_menu_keyboard(),
    )
    await callback_query.answer()

@dp.callback_query(F.data == 'menu_engine_control')
async def cq_show_engine_control_menu(callback_query: types.CallbackQuery):
    """'엔진 제어' 메뉴 표시"""
    await callback_query.message.edit_text(
        "⚙️ **엔진 제어**\n\n원하는 제어 버튼을 클릭하세요.",
        reply_markup=get_engine_control_menu_keyboard(),
    )
    await callback_query.answer()

@dp.callback_query(F.data == 'menu_order_management')
async def cq_show_order_management_menu(callback_query: types.CallbackQuery):
    """'주문 관리' 메뉴 표시"""
    await callback_query.message.edit_text(
        "🛒 **주문 관리**\n\n원하는 주문 버튼을 클릭하세요.",
        reply_markup=get_order_management_menu_keyboard(),
    )
    await callback_query.answer()

# --- 콜백 쿼리 핸들러 (기능 실행) ---

# '상태 및 정보' 기능
@dp.callback_query(F.data == 'show_status')
async def cq_status_handler(cq: types.CallbackQuery):
    reply_message = await get_status_message()
    await cq.message.answer(reply_message)
    await cq.answer()

@dp.callback_query(F.data == 'show_report')
async def cq_report_handler(cq: types.CallbackQuery):
    reply_message = await get_file_content_message(DAILY_REPORT_FILE, "일일 보고서")
    await cq.message.answer(reply_message)
    await cq.answer()

@dp.callback_query(F.data == 'show_logs')
async def cq_logs_handler(cq: types.CallbackQuery):
    reply_message = await get_file_content_message(LOG_FILE_PATH, "거래 로그")
    await cq.message.answer(reply_message)
    await cq.answer()

@dp.callback_query(F.data == 'show_errorlog')
async def cq_errorlog_handler(cq: types.CallbackQuery):
    reply_message = await get_file_content_message(ERROR_LOG_FILE_PATH, "에러 로그")
    await cq.message.answer(reply_message)
    await cq.answer()

# --- 공용 종목 선택 핸들러 ---

def get_symbol_selection_keyboard():
    """엔진 상태 파일에서 상위 심볼을 읽어 키보드를 생성합니다."""
    buttons = []
    try:
        if STATUS_FILE_PATH.exists():
            with open(STATUS_FILE_PATH, 'r', encoding='utf-8') as f:
                status_data = json.load(f)
            top_symbols = status_data.get("top_symbols", [])
            if top_symbols:
                # 한 줄에 3개씩 버튼 배치
                buttons = [InlineKeyboardButton(text=s, callback_data=f"select_symbol:{s}") for s in top_symbols]
                buttons = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    except Exception as e:
        logging.error(f"상태 파일 읽기 실패: {e}")
    
    buttons.append([InlineKeyboardButton(text="✍️ 직접 입력", callback_data="manual_symbol_input")])
    buttons.append([InlineKeyboardButton(text="취소", callback_data="show_help")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- 대화형 주문 (FSM) 핸들러 ---

@dp.callback_query(F.data.in_(['order_buy', 'order_sell']))
async def start_order_process(cq: types.CallbackQuery, state: FSMContext):
    """매수/매도 버튼 클릭 시 주문 프로세스 시작"""
    order_side = 'buy' if cq.data == 'order_buy' else 'sell'
    await state.update_data(side=order_side)
    
    keyboard = get_symbol_selection_keyboard()
    await cq.message.edit_text(
        f"<b>어떤 종목을 {'매수' if order_side == 'buy' else '매도'}하시겠습니까?</b>\n\n아래에서 선택하거나 직접 입력하세요.",
        reply_markup=keyboard
    )
    await cq.answer()

@dp.callback_query(F.data == 'manual_symbol_input')
async def cq_manual_symbol_input(cq: types.CallbackQuery, state: FSMContext):
    """직접 입력 버튼 처리"""
    await state.set_state(OrderForm.symbol) # 텍스트 입력을 기다리는 상태로 변경
    await cq.message.edit_text("종목 코드를 직접 입력하세요 (예: BTCUSDT).", reply_markup=None)
    await cq.answer()

@dp.callback_query(F.data.startswith('select_symbol:'))
async def cq_select_symbol_for_order(cq: types.CallbackQuery, state: FSMContext):
    """심볼 버튼 클릭 처리"""
    symbol = cq.data.split(":")[1]
    await state.update_data(symbol=symbol)
    await state.set_state(OrderForm.amount)
    await cq.message.edit_text(
        f"<b>{hcode(symbol)} 종목의 주문 수량을 입력하세요.</b>\n"
        "USDT 기준 수량입니다. 예: <code>10.5</code>\n"
        "취소하려면 /cancel 을 입력하세요."
    )
    await cq.answer()

@dp.message(OrderForm.symbol)
async def process_symbol(message: types.Message, state: FSMContext):
    """종목명을 입력받는 상태"""
    symbol = message.text.upper().strip()
    await state.update_data(symbol=symbol)
    await state.set_state(OrderForm.amount)
    await message.answer(
        f"<b>{hcode(symbol)} 종목의 주문 수량을 입력하세요.</b>\n"
        "USDT 기준 수량입니다. 예: <code>10.5</code>\n"
        "취소하려면 /cancel 을 입력하세요."
    )

@dp.message(OrderForm.amount)
async def process_amount(message: types.Message, state: FSMContext):
    """주문 수량을 입력받는 상태"""
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError("수량은 0보다 커야 합니다.")
    except ValueError:
        await message.reply("잘못된 수량입니다. 숫자만 입력해주세요. 예: <code>10.5</code>")
        return

    user_data = await state.get_data()
    await state.clear()

    side = user_data['side']
    symbol = user_data['symbol']
    
    # 최종 확인 메시지
    await message.answer(
        f"<b>주문 실행 요청</b>\n"
        f"- 종류: {'매수' if side == 'buy' else '매도'}\n"
        f"- 종목: {hcode(symbol)}\n"
        f"- 수량: {hcode(str(amount))} USDT\n\n"
        f"엔진에 주문을 전송합니다..."
    )

    # 엔진에 최종 명령어 전송
    await send_engine_command(
        message,
        command=f"order_{side}",
        params={"symbol": symbol, "amount": amount}
    )



# --- 전략 변경 (FSM) 핸들러 ---

@dp.callback_query(F.data == 'engine_switch_strategy')
async def start_strategy_switch(cq: types.CallbackQuery, state: FSMContext):
    """전략 변경 프로세스 시작 (버튼 선택 방식)"""
    strategies_dir = PROJECT_ROOT / "src" / "engine" / "strategies"
    buttons = []
    try:
        if strategies_dir.is_dir():
            for f in strategies_dir.glob("*.py"):
                if f.name != "__init__.py":
                    strategy_name = f.stem
                    buttons.append([InlineKeyboardButton(
                        text=strategy_name, 
                        callback_data=f"select_strategy:{strategy_name}"
                    )])
    except Exception as e:
        logging.error(f"전략 디렉토리 조회 실패: {e}")

    if not buttons:
        await cq.message.answer("사용 가능한 전략을 찾을 수 없습니다.")
        await cq.answer()
        return

    buttons.append([InlineKeyboardButton(text="취소", callback_data="show_help")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await cq.message.edit_text(
        "<b>변경할 전략을 선택하세요.</b>",
        reply_markup=keyboard
    )
    await cq.answer()

@dp.callback_query(F.data.startswith('select_strategy:'))
async def cq_select_strategy(cq: types.CallbackQuery, state: FSMContext):
    """전략 버튼 클릭 처리"""
    strategy_name = cq.data.split(":")[1]
    await state.update_data(strategy_name=strategy_name)
    await state.set_state(StrategyForm.model_path)
    
    await cq.message.edit_text(
        f"선택된 전략: {hcode(strategy_name)}\n\n"
        "<b>이제, 새로운 모델 파일의 경로를 입력하세요.</b>\n"
        "예: <code>outputs/models/your_model.zip</code>\n"
        "취소하려면 /cancel 을 입력하세요."
    )
    await cq.answer()


@dp.message(StrategyForm.model_path)
async def process_model_path(message: types.Message, state: FSMContext):
    """모델 경로를 입력받는 상태"""
    user_data = await state.get_data()
    strategy_name = user_data['strategy_name']
    model_path = message.text.strip()
    
    await state.clear()

    await message.answer(
        f"<b>전략 변경 요청</b>\n"
        f"- 전략 이름: {hcode(strategy_name)}\n"
        f"- 모델 경로: {hcode(model_path)}\n\n"
        f"엔진에 변경 명령을 전송합니다..."
    )

    await send_engine_command(
        message,
        command="engine_switch_strategy",
        params={"strategy_name": strategy_name, "model_path": model_path}
    )



# --- 대화형 TP/SL 설정 (FSM) 핸들러 ---

@dp.callback_query(F.data.in_(['order_tp', 'order_sl']))
async def start_tpsl_process(cq: types.CallbackQuery, state: FSMContext):
    """TP/SL 주문 프로세스 시작"""
    side = 'tp' if cq.data == 'order_tp' else 'sl'
    await state.update_data(side=side)
    
    keyboard = get_symbol_selection_keyboard() # 공용 함수 재사용
    side_text = "익절(TP)" if side == 'tp' else "손절(SL)"

    await cq.message.edit_text(
        f"<b>어떤 종목에 {side_text} 주문을 설정하시겠습니까?</b>\n\n아래에서 선택하거나 직접 입력하세요.",
        reply_markup=keyboard
    )
    await cq.answer()

# TP/SL을 위한 심볼 직접 입력 상태 전이
@dp.callback_query(F.data == 'manual_symbol_input', lambda query: query.message.text.startswith("어떤 종목에"))
async def cq_manual_symbol_input_tpsl(cq: types.CallbackQuery, state: FSMContext):
    await state.set_state(TPSLForm.symbol)
    await cq.message.edit_text("종목 코드를 직접 입력하세요 (예: BTCUSDT).", reply_markup=None)
    await cq.answer()

# TP/SL을 위한 심볼 버튼 선택 처리
@dp.callback_query(F.data.startswith('select_symbol:'), lambda query: query.message.text.startswith("어떤 종목에"))
async def cq_select_symbol_for_tpsl(cq: types.CallbackQuery, state: FSMContext):
    symbol = cq.data.split(":")[1]
    await state.update_data(symbol=symbol)
    await state.set_state(TPSLForm.price)
    
    user_data = await state.get_data()
    side_text = "익절(TP)" if user_data.get('side') == 'tp' else "손절(SL)"

    await cq.message.edit_text(
        f"선택된 종목: {hcode(symbol)}\n\n"
        f"<b>{side_text} 발동 가격을 입력하세요.</b>\n"
        f"예: <code>70000.5</code>\n"
        f"취소하려면 /cancel 을 입력하세요."
    )
    await cq.answer()


@dp.message(TPSLForm.symbol)
async def process_tpsl_symbol(message: types.Message, state: FSMContext):
    """TP/SL 종목명을 입력받는 상태"""
    await state.update_data(symbol=message.text.upper().strip())
    await state.set_state(TPSLForm.price)
    user_data = await state.get_data()
    side_text = "익절(TP)" if user_data['side'] == 'tp' else "손절(SL)"
    await message.answer(
        f"<b>{side_text} 발동 가격을 입력하세요.</b>\n"
        f"예: <code>70000.5</code>\n"
        f"취소하려면 /cancel 을 입력하세요."
    )

@dp.message(TPSLForm.price)
async def process_tpsl_price(message: types.Message, state: FSMContext):
    """TP/SL 가격을 입력받는 상태"""
    try:
        price = float(message.text.strip())
        if price <= 0:
            raise ValueError("가격은 0보다 커야 합니다.")
        await state.update_data(price=price)
        await state.set_state(TPSLForm.amount)
        await message.answer(
            "<b>주문 수량을 입력하세요.</b>\n"
            f"USDT 기준 수량입니다. 예: <code>10.5</code>\n"
            f"취소하려면 /cancel 을 입력하세요."
        )
    except ValueError:
        await message.reply("잘못된 가격입니다. 숫자만 입력해주세요. 예: <code>70000.5</code>")

@dp.message(TPSLForm.amount)
async def process_tpsl_amount(message: types.Message, state: FSMContext):
    """TP/SL 수량을 입력받는 상태"""
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError("수량은 0보다 커야 합니다.")
    except ValueError:
        await message.reply("잘못된 수량입니다. 숫자만 입력해주세요. 예: <code>10.5</code>")
        return

    user_data = await state.get_data()
    await state.clear()

    side = user_data['side']
    symbol = user_data['symbol']
    price = user_data['price']
    side_text = "익절(TP)" if side == 'tp' else "손절(SL)"

    await message.answer(
        f"<b>{side_text} 주문 실행 요청</b>\n"
        f"- 종목: {hcode(symbol)}\n"
        f"- 발동 가격: {hcode(str(price))}\n"
        f"- 수량: {hcode(str(amount))} USDT\n\n"
        f"엔진에 주문을 전송합니다..."
    )

    await send_engine_command(
        message,
        command=f"order_{side}",
        params={"symbol": symbol, "trigger_price": price, "amount": amount}
    )


# --- IPC 연동 기능 핸들러 (주문 제외) ---
@dp.callback_query(F.data.in_([
    'show_balance', 'show_summary', 'show_config', 
    'engine_stop', 'engine_restart', 'engine_run', 'engine_resume', 
    'order_close'
]))
async def cq_ipc_command_handler(cq: types.CallbackQuery):
    """모든 단순 IPC 연동 버튼이 이 핸들러를 통해 명령을 전송합니다."""
    await cq.answer() # 즉시 응답
    command_map = {
        'show_balance': 'get_balance',
        'show_summary': 'get_summary',
        'show_config': 'get_config',
    }
    command_to_send = command_map.get(cq.data, cq.data)
    # send_engine_command는 이제 message 객체를 첫 인자로 받으므로, cq.message를 전달합니다.
    await send_engine_command(cq.message, command_to_send)


# --- 기존 명령어 핸들러 (호환성 유지) ---

@dp.message(F.text.startswith("/status"))
async def command_status_handler(message: types.Message):
    reply_message = await get_status_message()
    await message.reply(reply_message)

@dp.message(F.text.startswith("/report"))
async def command_report_handler(message: types.Message):
    reply_message = await get_file_content_message(DAILY_REPORT_FILE, "일일 보고서")
    await message.reply(reply_message)

@dp.message(F.text.startswith("/logs"))
async def command_logs_handler(message: types.Message):
    reply_message = await get_file_content_message(LOG_FILE_PATH, "거래 로그")
    await message.reply(reply_message)

@dp.message(F.text.startswith("/errorlog"))
async def command_errorlog_handler(message: types.Message):
    reply_message = await get_file_content_message(ERROR_LOG_FILE_PATH, "에러 로그")
    await message.reply(reply_message)

# --- 백테스트 핸들러 (수정 없음) ---

@dp.message(F.text.startswith("/backtest"))
async def command_backtest_handler(message: types.Message):
    """
    /backtest <심볼> <시작일> [종료일] 형식의 명령어를 처리합니다.
    예: /backtest BTC/USDT 2025-08-01
    예: /backtest ETH/USDT 2025-07-01 2025-08-31
    """
    logging.info(f"/backtest 명령어를 수신했습니다 (from: {message.from_user.username}).")
    
    try:
        args = message.text.split(maxsplit=1) # 첫 번째 공백만 분리
        if len(args) < 2:
            await message.reply(
                "⚠️ 백테스트 인수가 부족합니다.\n"
                "사용법: `/backtest <인수들>`\n"
                "예시: `/backtest --symbol BTC/USDT --start_date 2025-08-01`",
                parse_mode="Markdown"
            )
            return

        # 나머지 인수를 공백으로 분리
        backtest_args = args[1].split()

        await message.reply(f"백테스트를 시작합니다: `{' '.join(backtest_args)}`\n잠시만 기다려주세요...", parse_mode="Markdown")

        python_executable = sys.executable
        script_path = PROJECT_ROOT / 'run_backtest.py'

        if not script_path.exists():
            logging.error(f"백테스트 스크립트를 찾을 수 없습니다: {script_path}")
            await message.reply("오류: `run_backtest.py`를 찾을 수 없습니다. 봇 설정이 잘못되었습니다.")
            return
        
        # 기존 인수와 --no_telegram을 합쳐서 전달
        cmd = [python_executable, str(script_path)] + backtest_args + ["--no_telegram"]


        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)

        stdout, stderr = await process.communicate()
        output_str = stdout.decode('utf-8', errors='ignore')
        error_str = stderr.decode('utf-8', errors='ignore')

        if process.returncode == 0:
            html_file_path = None
            for line in output_str.splitlines():
                if "Plot file saved to:" in line:
                    # 'Plot file saved to: ' 부분을 제거하고 경로를 얻습니다.
                    html_file_path = line.split("Plot file saved to:", 1)[1].strip()
                    break
            
            if html_file_path and Path(html_file_path).exists():
                await message.reply_document(
                    FSInputFile(html_file_path),
                    caption=f"✅ 백테스트 완료: `{' '.join(backtest_args)}`\n결과 보고서를 전송합니다."
                )
            else:
                await message.reply(f"✅ 백테스트는 완료되었지만, 결과 파일을 찾을 수 없습니다.\n\n**STDOUT:**\n```\n{output_str or 'No output'}\n```\n\n**STDERR:**\n```\n{error_str or 'No error'}\n```")
        else:
            logging.error(f"백테스트 실행 중 오류 발생:\n{error_str}")
            await message.reply(
                f"❌ 백테스트 실행 중 오류가 발생했습니다.\n"
                f"```\n{error_str or 'Unknown error'}\n```"
            )

    except Exception as e:
        logging.error(f"백테스트 명령어 처리 중 예외 발생: {e}", exc_info=True)
        await message.reply(f"백테스트 명령어를 처리하는 중 심각한 오류가 발생했습니다: {e}")

# --- 폴링 시작 ---
async def main():
    """디스패처를 시작하고 봇의 폴링을 시작합니다."""
    logging.info("텔레그램 봇 리스너를 시작합니다...")
    # dp.start_polling은 블로킹 함수이므로, awaitable을 직접 사용합니다.
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("사용자에 의해 프로그램이 중단되었습니다.")
    sys.exit(0)
