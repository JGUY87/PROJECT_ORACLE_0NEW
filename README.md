## 1. 프로젝트 개요 및 실행

### 실행 방법
1단계: 가상환경 생성 (Python 3.10.x 권장)  
python3.10 -m venv trading_env  
source trading_env/bin/activate  # Linux/Mac  
trading_env\Scripts\activate     # Windows  

2단계: pip 업그레이드 및 필수 패키지 설치  
pip install --upgrade pip setuptools wheel  
pip install -r requirements/base.txt  

3단계: 환경 설정 파일 (.env) 준비  
copy .env.example .env  # .env.example을 복사하여 .env 파일 생성 후 API 키 채우기  

.env 파일 내용 예시:  
BYBIT_API_KEY="YOUR_API_KEY"  
BYBIT_API_SECRET="YOUR_API_SECRET"  
BYBIT_TESTNET="true" # 실전매매 시 "false"로 변경  

4단계: 프로그램 실행  
python src/main_realtime.py   # 실시간 자동매매 실행  
python src/main_backtest.py   # 백테스팅 실행  

---

### 주요 변경 사항 (통합)
* BUY 편향 제거: strategy_recommender.py가 HOLD 기준을 명확히 도입.  
* main_realtime.py에서 action 정규화 + HOLD 시 주문 스킵.  
* market_features.py 계산 키 표준화 및 스냅샷 로깅 헬퍼.  
* 텔레그램 모듈 비동기 기본 + 동기 래퍼.  

### 주의 사항
* Bybit REST v5: category='linear', accountType='UNIFIED' 고정.  
* .env에서 DRY_RUN=true로 먼저 검증하세요.  

---

## 2. 핵심 모듈 (core) – ULTIMA v2 최적화

* v5 고정(category='linear'), 잔고 UNIFIED→CONTRACT 폴백, 안전 주문 래퍼  
* 데이터 피처/랭킹/급등감지 최소 의존(NumPy/Pandas)로 재작성  
* 전략추천: PPO 우선, 워뇨띠/TD/눌림/매집/EMA 폴백 일원화  
* 리포트/엔진 상태/거래로그 6컬럼 표준화  

### 주요 파일
* src/trade_executor_async.py  
* src/market_features.py  
* src/strategy_recommender.py  
* src/model_loader.py  
* src/report_utils.py  

### 사용 팁
* 주문은 기본적으로 tools.sitecustomize.preflight_and_place()를 경유하면 110007 자동 감량 재시도 활성화  
* 피처는 외부 데이터로 compute_features() 호출 → strategy_recommender.ai_recommend_strategy_strategy_live() 입력  

---

## 3. 도구 (tools) – ULTIMA v2

* 전역 프리플라이트(sitecustomize.py) + v5 진단 스크립트 + 네트워크 점검  
* 110007(잔고부족) 자동 감량 재시도 + 스텝/최소수량 보정 포함  

### 사용법
1. 전역 프리플라이트: 프로젝트 루트에 sitecustomize.py가 존재하고 내부에서 tools.sitecustomize.GLOBAL_PREFLIGHT_BOOT()를 호출하도록 구성하세요.  
2. v5 진단: python -m tools.diag_bybit_v5  
3. 네트워크 진단: python -m tools.diag_network  

---

## 4. Zip-only 최적화 (원본 정보)

이 패키지는 업로드하신 zip 내용만 최적화했습니다. (기존 폴더 최적화본은 건드리지 않음)  

### 적용 사항
* __pycache__/*.pyc 제거  
* 패키지 자동 보정: .py가 있는 폴더에 __init__.py 추가  
* 텍스트 파일(코드/설정/문서) UTF-8 + LF 표준화 (가능한 경우에 한함)  
* _original_backup/에 원본 그대로 보관  

### 사용
최적화된 이 zip을 프로젝트에 적용(덮어쓰기)해도 안전합니다. 파이썬 임포트/경로 이슈와 인코딩 문제를 줄여줍니다.  
