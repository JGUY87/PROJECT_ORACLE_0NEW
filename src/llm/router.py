from __future__ import annotations
import random
from typing import List, Optional, Dict, Any

from .providers import OpenAIProvider, AnthropicProvider, GeminiProvider, BaseProvider
from .types import LLMResponse

class ProviderPriority:
    """우선순위 전략 프리셋.
    - 'balanced': OpenAI -> Anthropic -> Gemini
    - 'reasoning': Anthropic -> OpenAI -> Gemini
    - 'speed': Gemini -> OpenAI -> Anthropic
    """
    balanced = ["openai", "anthropic", "gemini"]
    reasoning = ["anthropic", "openai", "gemini"]
    speed = ["gemini", "openai", "anthropic"]

PRIORITY_MAP = {
    "balanced": ProviderPriority.balanced,
    "reasoning": ProviderPriority.reasoning,
    "speed": ProviderPriority.speed,
}

class LLMRouter:
    def __init__(self, providers: Dict[str, BaseProvider]):
        self.providers = providers

    @classmethod
    def from_env(cls) -> "LLMRouter":
        provs: Dict[str, BaseProvider] = {}
        o = OpenAIProvider()
        if o.available():
            provs[o.name] = o
        a = AnthropicProvider()
        if a.available():
            provs[a.name] = a
        g = GeminiProvider()
        if g.available():
            provs[g.name] = g
        return cls(provs)

    def complete(self, prompt: str, strategy: str = "balanced", **kw: Any) -> LLMResponse:
        order = PRIORITY_MAP.get(strategy, ProviderPriority.balanced)
        errors = []
        for name in order:
            p = self.providers.get(name)
            if not p:
                continue
            try:
                return p.complete(prompt, **kw)
            except Exception as e:  # pragma: no cover - network dependent
                errors.append(f"{name}: {e}")
        raise RuntimeError("모든 프로바이더 실패: " + " | ".join(errors))

    def fanout(self, prompt: str, providers: Optional[List[str]] = None, **kw: Any) -> List[LLMResponse]:
        targets = providers or list(self.providers.keys())
        results: List[LLMResponse] = []
        for name in targets:
            p = self.providers.get(name)
            if not p:
                continue
            try:
                results.append(p.complete(prompt, **kw))
            except Exception as e:  # pragma: no cover
                results.append(LLMResponse(provider=name, text=f"__ERROR__: {e}"))
        return results

    def race(self, prompt: str, providers: Optional[List[str]] = None, **kw: Any) -> LLMResponse:
        # 단순 구현: 무작위 셔플 후 첫 성공 반환 (동기)
        targets = providers or list(self.providers.keys())
        random.shuffle(targets)
        for name in targets:
            p = self.providers.get(name)
            if not p:
                continue
            try:
                return p.complete(prompt, **kw)
            except Exception:
                continue
        raise RuntimeError("race 실패: 모든 프로바이더 실패")

__all__ = ["LLMRouter", "ProviderPriority"]
