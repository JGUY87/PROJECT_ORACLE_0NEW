# LLM Multi-Provider Layer

간단한 다중 LLM(OpenAI / Anthropic / Gemini) 라우터.

## 설치 (선택 라이브러리)
```
pip install openai anthropic google-generativeai
```

## 환경 변수
```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
```

## 사용 예시
```python
from src.llm.router import LLMRouter
router = LLMRouter.from_env()
resp = router.complete("Explain PPO briefly", strategy="balanced")
print(resp.provider, resp.text)
```

## 전략
- balanced: OpenAI -> Anthropic -> Gemini
- reasoning: Anthropic -> OpenAI -> Gemini
- speed: Gemini -> OpenAI -> Anthropic

## 고급
- fanout(prompt): 모든 사용가능 프로바이더 호출 후 리스트 반환
- race(prompt): 무작위 순서로 첫 성공 반환

## 향후 개선 아이디어
- 비동기 aiohttp/httpx 기반 병렬
- 토큰 비용 추정 & 예산 제어
- 품질 스코어링(길이, 키워드, 금지패턴)
- 캐시 (prompt hash -> response)
