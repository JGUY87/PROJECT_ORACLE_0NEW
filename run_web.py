# -*- coding: utf-8 -*-
"""
FastAPI 웹서버 실행 스크립트 (uvicorn 사용)
"""
import uvicorn

if __name__ == "__main__":
    # uvicorn.run()을 호출하여 웹 서버를 시작합니다.
    # "src.web.main:app"는 "src/web/main.py" 파일의 app 인스턴스를 의미합니다.
    # reload=True는 코드 변경 시 서버를 자동으로 재시작해주는 개발용 옵션입니다.
    uvicorn.run(
        "src.web.main:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=True
    )
