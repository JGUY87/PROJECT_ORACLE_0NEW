"""LLM multi-provider adapters (OpenAI, Anthropic, Google Gemini)

Usage example:

from src.llm.router import LLMRouter, ProviderPriority
router = LLMRouter.from_env()
resp = router.complete("Explain PPO in 2 sentences", strategy="balanced")
print(resp.text)
"""
from .types import LLMResponse  # noqa: F401
