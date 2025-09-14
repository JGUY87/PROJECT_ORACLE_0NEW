# -*- coding: utf-8 -*-
"""
notifier/core/send_report_telegram.py (v2) — async 기본 + sync 래퍼 + 이미지 전송
"""
from __future__ import annotations
import os
import asyncio
from typing import Optional, Dict, Any

try:
    import aiohttp
except Exception:
    aiohttp = None

API_SEND_TEXT  = "https://api.telegram.org/bot{token}/sendMessage"
API_SEND_PHOTO = "https://api.telegram.org/bot{token}/sendPhoto"

def _resolve_token_chat(chat_id: Optional[str]=None, token: Optional[str]=None) -> tuple[str,str]:
    tok = token or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
    cid = chat_id or os.getenv("TELEGRAM_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
    if not tok or not cid:
        raise RuntimeError("TELEGRAM 토큰/채팅ID 없음")
    return str(tok), str(cid)

async def _post_json(url: str, data: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    if aiohttp is None:
        raise RuntimeError("aiohttp 미설치")
    timeout_cfg = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=timeout_cfg) as sess:
        async with sess.post(url, json=data) as resp:
            resp.raise_for_status()
            return await resp.json()

async def send_telegram_message(
    text: str, chat_id: Optional[str] = None, token: Optional[str] = None,
    parse_mode: Optional[str] = None, disable_web_page_preview: bool = True, timeout: int = 15
) -> Dict[str, Any]:
    """텔레그램으로 텍스트 메시지를 비동기 전송합니다."""
    try:
        tok, cid = _resolve_token_chat(chat_id, token)
        url = API_SEND_TEXT.format(token=tok)
        payload = {
            "chat_id": cid,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        
        return await _post_json(url, payload, timeout)
    except Exception as e:
        # 로깅 또는 에러 처리를 여기에 추가할 수 있습니다.
        print(f"Telegram 메시지 전송 실패: {e}")
        return {"ok": False, "description": str(e)}

def send_telegram_message_sync(
    text: str, chat_id: Optional[str] = None, token: Optional[str] = None,
    parse_mode: Optional[str] = None, disable_web_page_preview: bool = True, timeout: int = 15
):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(send_telegram_message(text, chat_id, token, parse_mode, disable_web_page_preview, timeout))
    else:
        return loop.create_task(send_telegram_message(text, chat_id, token, parse_mode, disable_web_page_preview, timeout))