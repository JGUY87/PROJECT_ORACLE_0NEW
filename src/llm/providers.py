from __future__ import annotations
import os
import time
from typing import Any, Optional

from .types import LLMResponse

try:
    import openai  # type: ignore
except ImportError:  # pragma: no cover
    openai = None  # type: ignore

try:
    import anthropic  # type: ignore
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore

try:
    import google.generativeai as genai  # type: ignore
except ImportError:  # pragma: no cover
    genai = None  # type: ignore


class BaseProvider:
    name: str = "base"
    supports_system: bool = True

    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, prompt: str, **kw: Any) -> LLMResponse:  # pragma: no cover - abstract
        raise NotImplementedError


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        super().__init__(api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model
        if openai and self.api_key:
            if hasattr(openai, "api_key"):
                openai.api_key = self.api_key  # legacy

    def complete(self, prompt: str, **kw: Any) -> LLMResponse:
        if not openai:
            raise RuntimeError("openai 패키지가 설치되지 않았습니다. 'pip install openai' 필요")
        start = time.perf_counter()
        # 최신 responses API 사용 가능 시 분기 (단순화)
        client = getattr(openai, "OpenAI", None)
        raw = None
        if client:
            cli = client(api_key=self.api_key)
            raw = cli.responses.create(model=self.model, input=prompt, **{k: v for k, v in kw.items() if v is not None})
            text = raw.output_text  # type: ignore
            usage = getattr(raw, "usage", None)
            pt = getattr(usage, "input_tokens", None) if usage else None
            ct = getattr(usage, "output_tokens", None) if usage else None
        else:  # fallback legacy
            raw = openai.ChatCompletion.create(model=self.model, messages=[{"role": "user", "content": prompt}], **kw)
            text = raw["choices"][0]["message"]["content"]
            usage = raw.get("usage", {})
            pt = usage.get("prompt_tokens")
            ct = usage.get("completion_tokens")
        latency = (time.perf_counter() - start) * 1000
        return LLMResponse(provider=self.name, text=text, prompt_tokens=pt, completion_tokens=ct, latency_ms=latency, raw=getattr(raw, "model_dump", lambda: raw)())


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-latest"):
        super().__init__(api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.model = model
        self._client = anthropic.Anthropic(api_key=self.api_key) if (anthropic and self.api_key) else None

    def complete(self, prompt: str, **kw: Any) -> LLMResponse:
        if not self._client:
            raise RuntimeError("anthropic 패키지 또는 API 키 미설정")
        start = time.perf_counter()
        raw = self._client.messages.create(model=self.model, max_tokens=kw.get("max_tokens", 512), messages=[{"role": "user", "content": prompt}])
        txt = "".join(block.text for block in raw.content if getattr(block, "type", None) == "text")
        usage = getattr(raw, "usage", None)
        pt = getattr(usage, "input_tokens", None) if usage else None
        ct = getattr(usage, "output_tokens", None) if usage else None
        latency = (time.perf_counter() - start) * 1000
        return LLMResponse(provider=self.name, text=txt, prompt_tokens=pt, completion_tokens=ct, latency_ms=latency, raw=raw.model_dump())


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        super().__init__(api_key or os.getenv("GOOGLE_API_KEY"))
        self.model = model
        if genai and self.api_key:
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(self.model)
        else:
            self._model = None

    def complete(self, prompt: str, **kw: Any) -> LLMResponse:
        if not self._model:
            raise RuntimeError("google-generativeai 패키지 또는 API 키 미설정")
        start = time.perf_counter()
        raw = self._model.generate_content(prompt)
        txt = getattr(raw, "text", None) or (raw.candidates[0].content.parts[0].text if raw.candidates else "")
        usage = getattr(raw, "usage_metadata", None)
        pt = getattr(usage, "prompt_token_count", None) if usage else None
        ct = getattr(usage, "candidates_token_count", None) if usage else None
        latency = (time.perf_counter() - start) * 1000
        return LLMResponse(provider=self.name, text=txt, prompt_tokens=pt, completion_tokens=ct, latency_ms=latency, raw=getattr(raw, "__dict__", {}))


__all__ = [
    "OpenAIProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "BaseProvider",
]
