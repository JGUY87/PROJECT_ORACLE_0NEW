# -*- coding: utf-8 -*-
"""
src/core/balance_utils.py

Fetches USDT balance from the engine and converts it to KRW.
"""
import requests
import asyncio
from src import command_manager as cm

async def _get_usdt_balance_from_engine() -> float:
    """Helper to get just the USDT value from the engine."""
    try:
        result = await cm.send_command("get_balance", timeout=10)
        if result and result.get("status") == "success":
            # The data is returned as a string, so parse it.
            usdt_str = result.get("data", {}).get("USDT", "0.0")
            return float(usdt_str)
    except Exception as e:
        print(f"Could not get balance from engine: {e}")
    return 0.0

async def get_usdt_balance_and_krw() -> dict:
    """
    Gets USDT balance from the engine and calculates KRW value using an external API.
    """
    usdt_balance = await _get_usdt_balance_from_engine()
    
    total_krw = 0
    usdkrw_rate = "N/A"
    rate_source = "N/A"

    try:
        rate_response = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        rate_response.raise_for_status()
        rate_data = rate_response.json()
        rate = rate_data.get("rates", {}).get("KRW")
        if rate:
            usdkrw_rate = rate
            rate_source = "exchangerate-api"
            total_krw = int(usdt_balance * usdkrw_rate)
    except Exception as e:
        print(f"Failed to get KRW exchange rate: {e}")
        usdkrw_rate = 1300  # Fallback
        rate_source = "Fallback"
        total_krw = int(usdt_balance * usdkrw_rate)

    return {
        "total_krw": total_krw,
        "usdt_balance": f"{usdt_balance:,.2f}",
        "usdkrw": f"{usdkrw_rate:,.0f}",
        "rate_source": rate_source
    }
