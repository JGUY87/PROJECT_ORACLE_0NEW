from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

@dataclass
class LLMResponse:
    provider: str
    text: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.text
