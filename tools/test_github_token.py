import os
import sys
import json
from typing import Optional

try:
    import requests  # type: ignore
except ImportError:
    print("[ERROR] requests 패키지가 설치되어 있지 않습니다. 'pip install requests' 후 다시 실행하세요.")
    sys.exit(1)

TOKEN = os.getenv("GITHUB_MCP_TOKEN") or os.getenv("GITHUB_TOKEN")
if not TOKEN:
    print("[FAIL] 환경 변수 GITHUB_MCP_TOKEN 또는 GITHUB_TOKEN 이 설정되지 않았습니다.")
    sys.exit(2)

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

resp = requests.get("https://api.github.com/user", headers=headers, timeout=15)
print("[INFO] HTTP Status:", resp.status_code)
if resp.status_code != 200:
    print("[FAIL] 토큰이 유효하지 않거나 권한이 부족합니다.")
    try:
        print("[DEBUG] Response:", resp.text[:400])
    except Exception:
        pass
    sys.exit(3)

data = resp.json()
print("[OK] 인증 성공. 로그인 계정:", data.get("login"))
scopes: Optional[str] = resp.headers.get("X-OAuth-Scopes")
if scopes:
    print("[INFO] 토큰 Scopes:", scopes)
else:
    print("[WARN] 토큰 스코프 헤더가 비어있습니다. (Fine-grained 토큰일 가능성)")

rate_limit = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=15)
if rate_limit.status_code == 200:
    rl = rate_limit.json()
    core = rl.get("resources", {}).get("core", {})
    print("[INFO] Rate Limit 남은 요청:", core.get("remaining"), "/", core.get("limit"))
else:
    print("[WARN] rate_limit 조회 실패:", rate_limit.status_code)
