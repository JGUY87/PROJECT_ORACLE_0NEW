# GitHub MCP 서버 연동 가이드

이 문서는 GitHub Model Context Protocol(MCP) 서버를 로컬/에이전트 환경에 연동하여 코드를 질의/편집/메타데이터 조회할 수 있게 하는 최소 설정 예시입니다.

## 1. 목표 정의 체크리스트
원하는 사용 범위를 결정 후 필요한 OAuth/PAT scope 최소화:
- 읽기 전용: repo:read (Private 포함 시 repo), read:org
- 이슈/PR 코멘트 작성: repo, pull_requests, issues
- Actions 상태 조회: repo, workflow
- Projects 사용: project (classic) / project:read (beta)

## 2. GitHub Personal Access Token 생성
1. https://github.com/settings/tokens (Fine-grained 권장)
2. Repository access: 필요한 범위(특정 혹은 전체)
3. Permissions 최소 부여 (예: Contents: Read, Metadata: Read, Pull requests: Read)
4. 토큰 생성 후 즉시 안전한 비밀 저장소(예: 1Password, Bitwarden)에 보관
5. 로컬 환경 변수 등록 (PowerShell / CMD 예시)

CMD:
```
set GITHUB_MCP_TOKEN=ghp_xxxxxxxxxxxxxxxxx
```
PowerShell:
```
$Env:GITHUB_MCP_TOKEN="ghp_xxxxxxxxxxxxxxxxx"
```
(지속화를 원하면 사용자 환경 변수에 추가)

## 3. MCP 클라이언트 설정 예시
아래 예시는 (가상의) node 기반 GitHub MCP 서버 바이너리 `github-mcp-server` 를 사용한다고 가정.
클라이언트별 설정 위치(예):
- Claude Desktop: ~/Library/Application Support/Claude/mcp/servers.json (Win: %APPDATA%\Claude\mcp)
- VS Code 확장(향후): .vscode/mcp.json

servers.json 항목 예시:
```json
{
  "github": {
    "command": "node",
    "args": ["/absolute/path/github-mcp-server/dist/index.js"],
    "env": {"GITHUB_TOKEN": "${GITHUB_MCP_TOKEN}"},
    "disabled": false
  }
}
```
(실제 사용 시 서버 구현체 경로로 교체)

## 4. 대안: gh CLI 래핑 (실험적)
공식 MCP 서버가 없다면 임시 어댑터 작성:
- Node/Python에서 stdin/stdout JSON-RPC 루프
- 요청 메서드 ↔ gh CLI 명령 매핑 (예: repos.get, pulls.list → `gh api`)
- Rate limit 헤더는 X-RateLimit-* 반환 필드로 노출

## 5. 간단 검증 스크립트 (토큰 유효성)
`tools/test_github_token.py` 예시 (원하면 생성 요청):
```python
import os, requests
TOKEN = os.getenv("GITHUB_MCP_TOKEN") or os.getenv("GITHUB_TOKEN")
assert TOKEN, "GITHUB_MCP_TOKEN not set"
resp = requests.get("https://api.github.com/user", headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})
print("Status:", resp.status_code)
print(resp.json().get("login"))
```

## 6. 권장 환경 변수 (.env 주석 템플릿)
```
# GitHub MCP
# GITHUB_MCP_TOKEN="your_fine_grained_pat"
# GITHUB_MCP_REPO_FILTER="owner1/repoA,owner2/repoB"
```
애플리케이션 코드에서 `os.getenv("GITHUB_MCP_REPO_FILTER", "")` 로 필터 목록 처리.

## 7. 보안 & 운영
- PAT는 최소 scope / 주기적 재발급 (90일 주기 권장)
- 로그에 Authorization 헤더 절대 출력 금지 (필요 시 `****` 마스킹)
- Rate limit 초과(403, X-RateLimit-Remaining=0) 시 지수 백오프

## 8. 추후 확장 아이디어
- 캐싱 Layer: repo tree / last commit SHA (TTL 60s)
- Embedding 인덱스(선택): README, 주요 폴더 요약 후 MCP tool 로 제공
- 병렬 fetch 시 2~4 동시 요청 제한 (Rate limiting)

## 9. 필요한 추가 정보 (피드백 요청)
- 사용할 MCP 클라이언트 종류? (Claude / Cursor / 기타)
- 필요한 GitHub 기능 범위? (코드 검색, PR 작성, 코멘트, 리뷰)
- 사내 프록시/방화벽 여부?

위 3가지를 알려주시면 맞춤 설정(JSON 샘플, 어댑터 코드 골격) 추가 제공 가능.
