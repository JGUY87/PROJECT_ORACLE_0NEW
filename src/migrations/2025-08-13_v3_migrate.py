# -*- coding: utf-8 -*- 
""" >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\migrations\2025-08-13_v3_migrate.py" && echo src/migrations/2025-08-13_v3_migrate.py >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\migrations\2025-08-13_v3_migrate.py" && echo - 구버전 settings.json의 키를 v3 스키마로 승격하는 마이그레이션 스크립트 >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\migrations\2025-08-13_v3_migrate.py" && echo """  
import json  
from pathlib import Path  
""  
# 새로운 프로젝트 구조에 맞게 settings.json 경로 설정  
# src/migrations/2025-08-13_v3_migrate.py 기준:  
# ../../configs/settings.json  
SETTINGS_PATH = Path(__file__).parent.parent.parent / "configs" / "settings.json"  
""  
def migrate():  
""" >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\migrations\2025-08-13_v3_migrate.py" && echo settings.json 파일을 읽어 v3 스키마로 마이그레이션합니다. >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\migrations\2025-08-13_v3_migrate.py" && echo """  
if not SETTINGS_PATH.exists():  
print("settings.json not found")  
return 
try:  
s = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))  
except Exception as e:  
print(f"settings.json 파싱 실패: {e}. 마이그레이션을 건너뜁니다.")  
return  
""  
# 샘플 마이그레이션 로직  
if "strategy" in s and "engine" not in s:  
s["engine"] = {"strategy": s.pop("strategy"), "symbol": s.get("symbol","BTCUSDT"), "timeframe": s.get("timeframe","1m"), "category":"linear","accountType":"UNIFIED","testnet":bool(s.get("testnet",False))}  
if "risk" not in s:  
s["risk"] = {"max_leverage":10,"daily_loss_cut_pct":0.07,"per_trade_risk_pct":0.01,"max_concurrent_positions":1}  
""  
try:  
SETTINGS_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")  
print("[OK] settings.json이 v3 형식으로 마이그레이션되었습니다.") 
except Exception as e:  
print(f"마이그레이션된 settings.json 저장 실패: {e}")  
""  
if __name__ == "__main__":  
migrate() 
