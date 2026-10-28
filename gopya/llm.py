"""A minimal client for any OpenAI-compatible chat completions endpoint (Groq, Ollama, vLLM)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model: str


class LlmError(Exception):
    pass


class ChatClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 20):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def complete(self, system: str, user: str, max_tokens: int = 400) -> Completion:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout_s)
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage") or {}
            return Completion(
                text=data["choices"][0]["message"]["content"] or "",
                tokens_in=int(usage.get("prompt_tokens", 0)),
                tokens_out=int(usage.get("completion_tokens", 0)),
                model=data.get("model", self.model),
            )
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LlmError(str(e)) from e
