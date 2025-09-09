# -*- coding: utf-8 -*- 
""" >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\migrations\set_wonyotti_tp1r_0_8.py" && echo src/migrations/set_wonyotti_tp1r_0_8.py >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\migrations\set_wonyotti_tp1r_0_8.py" && echo - 기존 strategy_overrides.json에 wonyotti.tp1_r=0.8을 병합 추가 >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\migrations\set_wonyotti_tp1r_0_8.py" && echo """  
from __future__ import annotations  
import json  
from pathlib import Path  
""  
# 새로운 프로젝트 구조에 맞게 strategy_overrides.json 경로 설정  
# src/migrations/set_wonyotti_tp1r_0_8.py 기준:  
# ../../configs/strategy_overrides.json  
PATH_TO_OVERRIDES = Path(__file__).parent.parent.parent / "configs" / "strategy_overrides.json"  
""  
def migrate():  
""" >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\migrations\set_wonyotti_tp1r_0_8.py" && echo strategy_overrides.json 파일을 읽어 wonyotti.tp1_r 값을 0.8로 설정합니다. >> "C:\Users\HP\AppData\Local\Temp\PROJECT_ORACLE_0_NEW\src\migrations\set_wonyotti_tp1r_0_8.py" && echo """  
data = {} 
if path.exists():  
try:  
data = json.loads(path.read_text(encoding="utf-8"))  
except Exception:  
data = {}  
""  
if "strategies" not in data or not isinstance(data["strategies"], dict):  
data["strategies"] = {}  
""  
if "wonyotti" not in data["strategies"] or not isinstance(data["strategies"]["wonyotti"], dict):  
data["strategies"]["wonyotti"] = {}  
""  
data["strategies"]["wonyotti"]["tp1_r"] = 0.8  
""  
path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8") 
print("[OK] set wonyotti.tp1_r = 0.8 in", path.as_posix())  
except Exception as e:  
print(f"마이그레이션된 strategy_overrides.json 저장 실패: {e}")  
""  
if __name__ == "__main__":  
migrate() 
