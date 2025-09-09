# -*- coding: utf-8 -*- 
""" >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\engine\leverage_helper.py" && echo src/engine/leverage_helper.py >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\engine\leverage_helper.py" && echo - CCXT를 사용하여 거래소 레버리지 설정 및 확인 >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\engine\leverage_helper.py" && echo """  
import asyncio  
import ccxt # pybit 대신 ccxt 임포트  
import logging # 로깅 추가  
""  
async def ensure_leverage(client: ccxt.Exchange, symbol: str, lev: float) - 
""" >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\engine\leverage_helper.py" && echo 지정된 심볼의 레버리지를 확인하고 필요시 설정합니다. >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\engine\leverage_helper.py" && echo Args: >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\engine\leverage_helper.py" && echo client (ccxt.Exchange): CCXT 거래소 클라이언트 객체. >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\engine\leverage_helper.py" && echo symbol (str): 거래 심볼 (예: 'BTC/USDT:USDT'). >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\engine\leverage_helper.py" && echo lev (float): 설정할 레버리지 값. >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\engine\leverage_helper.py" && echo """  
try:  
# CCXT를 사용하여 포지션 정보 가져오기  
# fetch_positions는 리스트를 반환하므로, 해당 심볼의 포지션을 찾아야 함 
positions = await client.fetch_positions(symbols=[symbol])  
pos = None  
for p in positions:  
if p['symbol'] == symbol:  
pos = p  
break  
""  
if not pos:  
logging.info(f"[LEVERAGE] {symbol}: 현재 포지션 없음. 레버리지 설정 건너뜀.")  
return  
""  
current_lev = float(pos.get("leverage", 0))  
""  
# 현재 레버리지가 다르면 설정  
if int(current_lev) != int(lev): 
# CCXT를 사용하여 레버리지 설정  
# set_leverage는 거래소마다 파라미터가 다를 수 있으므로 주의  
# Bybit의 경우, symbol, leverage, params={'marginMode': 'cross' or 'isolated'}  
await client.set_leverage(symbol=symbol, leverage=lev)  
logging.info(f"[LEVERAGE] {symbol} 레버리지 {current_lev} -> {lev}으로 설정 완료.")  
else:  
logging.info(f"[LEVERAGE] {symbol} 레버리지 이미 {lev}으로 설정되어 있음.")  
""  
except ccxt.ExchangeError as e:  
logging.error(f"[LEVERAGE] {symbol} 레버리지 설정 중 거래소 오류: {e}")  
except Exception as e:  
logging.exception(f"[LEVERAGE] {symbol} 레버리지 설정 중 예상치 못한 오류: {e}") 
