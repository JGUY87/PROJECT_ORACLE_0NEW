# -*- coding: utf-8 -*-
"""
src/dashboard/streamlit/app.py — Streamlit 대시보드

사용법:
streamlit run src/dashboard/streamlit/app.py

환경 변수:
API_BASE=http://localhost:8000  (FastAPI 서버와 연동)
"""
import os
import time
import requests
import pandas as pd
import streamlit as st
from typing import Dict, Any, List

# --- 설정 ---
API_BASE_URL = os.environ.get("API_BASE", "http://localhost:8000/api")
st.set_page_config(page_title="PROJECT_ORACLE_0 대시보드", layout="wide")

# --- 헬퍼 함수 ---
@st.cache_data(ttl=5) # 과도한 API 호출을 방지하기 위해 5초간 데이터 캐시
def fetch_data(endpoint: str) -> Dict[str, Any]:
    """주어진 API 엔드포인트에서 JSON 데이터를 가져옵니다."""
    try:
        response = requests.get(f"{API_BASE_URL}/{endpoint}")
        response.raise_for_status() # 잘못된 상태 코드에 대해 예외 발생
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"{endpoint}에 대한 API 요청 실패: {e}")
        return {}

# --- UI 레이아웃 ---
st.title("PROJECT_ORACLE_0 - 실시간 트레이딩 대시보드")

# 메인 메트릭 플레이스홀더
col1, col2, col3 = st.columns(3)
with col1:
    st_strategy = st.empty()
    st_symbol = st.empty()
with col2:
    st_equity = st.empty()
    st_mode = st.empty()
with col3:
    st_balance = st.empty()
    st_rate = st.empty()

st.divider()

# 차트 및 로그 플레이스홀더
col_chart, col_logs = st.columns([2, 1])
with col_chart:
    st.subheader("자산 곡선 (Equity Curve)")
    chart_placeholder = st.empty()

with col_logs:
    st.subheader("실시간 로그")
    logs_placeholder = st.empty()

st.divider()

# 거래 내역 테이블 플레이스홀더
st.subheader("최근 거래 내역")
trades_placeholder = st.empty()

# --- 실시간 업데이트를 위한 메인 루프 ---
while True:
    # 모든 엔드포인트에서 데이터 가져오기
    status_data = fetch_data("status")
    balance_data = fetch_data("balance")
    trades_data = fetch_data("trades?limit=50")
    logs_data = fetch_data("logs?limit=100")

    # --- 메트릭 업데이트 ---
    strategy = status_data.get("strategy", "-")
    symbol = status_data.get("symbol", "-")
    equity = status_data.get("equity", 0)
    mode = status_data.get("mode", "-")
    total_krw = balance_data.get("total_krw", 0)
    usdkrw_rate = balance_data.get("usdkrw", "?")
    rate_source = balance_data.get("rate_source", "?")

    st_strategy.metric("전략", strategy)
    st_symbol.metric("심볼", symbol)
    st_equity.metric("자산 (Equity)", f"{equity:,.2f} USDT")
    st_mode.write(f"**모드:** {mode}")
    st_balance.metric("추정 총 자산", f"{total_krw:,.0f} 원")
    st_rate.caption(f"환율: {usdkrw_rate} ({rate_source})")

    # --- 차트 업데이트 ---
    # 이제 차트는 FastAPI 백엔드에서 제공하는 이미지입니다.
    chart_url = f"{API_BASE_URL}/equity_chart.png?ts={int(time.time())}"
    chart_placeholder.image(chart_url, use_column_width=True)

    # --- 로그 업데이트 ---
    logs = logs_data.get("lines", [])
    logs_placeholder.code("\n".join(logs), language="text")

    # --- 거래 내역 테이블 업데이트 ---
    trades = trades_data.get("rows", [])
    if trades:
        df = pd.DataFrame(trades)
        # 가독성을 위해 열 순서 재정렬
        df = df[["ts", "side", "symbol", "qty", "ret"]]
        trades_placeholder.dataframe(df, use_container_width=True, hide_index=True)
    else:
        trades_placeholder.write("거래 내역이 없습니다.")

    # --- 새로고침 간격 ---
    time.sleep(5)
