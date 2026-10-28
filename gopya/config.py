"""Paths and settings. Every setting can be overridden with an environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    docs_dir: Path = Path(_env("GOPYA_DOCS_DIR", str(ROOT / "data" / "docs")))
    roles_file: Path = Path(_env("GOPYA_ROLES_FILE", str(ROOT / "data" / "roles.toml")))
    users_file: Path = Path(_env("GOPYA_USERS_FILE", str(ROOT / "data" / "users.toml")))
    index_dir: Path = Path(_env("GOPYA_INDEX_DIR", str(ROOT / "var" / "index")))
    trace_file: Path = Path(_env("GOPYA_TRACE_FILE", str(ROOT / "var" / "traces.jsonl")))

    top_k: int = int(_env("GOPYA_TOP_K", "4"))
    # Below this fused relevance the question is treated as "not in your documents".
    min_relevance: float = float(_env("GOPYA_MIN_RELEVANCE", "0.15"))
    # The offline answerer needs a sentence covering at least this share of the question's
    # (IDF-weighted) terms. Chosen with the sweep in eval/results/offline.json.
    min_coverage: float = float(_env("GOPYA_MIN_COVERAGE", "0.38"))

    # Any OpenAI-compatible chat endpoint. Groq's free tier is the default because it needs no
    # card; Ollama (http://localhost:11434/v1) works the same way.
    llm_base_url: str = _env("GOPYA_LLM_BASE_URL", "https://api.groq.com/openai/v1")
    llm_api_key: str = _env("GOPYA_LLM_API_KEY", os.environ.get("GROQ_API_KEY", ""))
    llm_model: str = _env("GOPYA_LLM_MODEL", "llama-3.3-70b-versatile")
    llm_timeout_s: float = float(_env("GOPYA_LLM_TIMEOUT_S", "20"))

    # Tokens one user may spend on the model per day before Gopya falls back to the offline
    # extractive answerer.
    daily_token_budget: int = int(_env("GOPYA_DAILY_TOKEN_BUDGET", "60000"))

    # USD per million tokens (input, output). Check the provider's price page before relying on
    # these: they are what Groq listed when this was written.
    prices: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {
            "llama-3.3-70b-versatile": (0.59, 0.79),
            "llama-3.1-8b-instant": (0.05, 0.08),
            "openai/gpt-oss-20b": (0.10, 0.50),
            "openai/gpt-oss-120b": (0.15, 0.75),
        }
    )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key) or "localhost" in self.llm_base_url


def settings() -> Settings:
    return Settings()
