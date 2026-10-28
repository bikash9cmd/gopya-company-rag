"""Request traces, cost and the per-user daily budget.

Every request is one JSON line: who asked (user and role, never a token), what the guards decided,
which chunks were retrieved, how long each stage took, and the tokens and cost of the model call.
`python -m gopya stats` summarises the file; in production the same records go to Azure Monitor
or LangSmith through an exporter.
"""

from __future__ import annotations

import json
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def cost_usd(prices: dict[str, tuple[float, float]], model: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = prices.get(model, (0.0, 0.0))
    return round((tokens_in * p_in + tokens_out * p_out) / 1_000_000, 6)


@dataclass
class Trace:
    user: str
    role: str
    question: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    decision: str = ""
    retrieved: list[str] = field(default_factory=list)
    top_score: float = 0.0
    backend: str = ""
    model: str = ""
    gate: str = ""
    redactions: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    ms: dict[str, float] = field(default_factory=dict)
    _t0: float = field(default_factory=time.perf_counter, repr=False)
    _last: float = field(default=0.0, repr=False)

    def lap(self, stage: str) -> None:
        now = time.perf_counter()
        start = self._last or self._t0
        self.ms[stage] = round((now - start) * 1000, 2)
        self._last = now

    def finish(self) -> dict:
        self.ms["total"] = round((time.perf_counter() - self._t0) * 1000, 2)
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class TraceLog:
    def __init__(self, path: Path | None):
        self.path = path
        self._spent: dict[tuple[str, str], int] = defaultdict(int)

    def write(self, record: dict) -> None:
        self._spent[(record["user"], record["ts"][:10])] += record["tokens_in"] + record["tokens_out"]
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def spent_today(self, user: str) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return self._spent[(user, today)]


def summarise(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    if not rows:
        return {"requests": 0}
    totals = [r["ms"]["total"] for r in rows]
    by_role = Counter(r["role"] for r in rows)
    decisions = Counter(r["decision"] for r in rows)
    gates = Counter(r["gate"].split(":")[0] for r in rows if r["gate"])
    q = statistics.quantiles(totals, n=20) if len(totals) > 1 else totals * 19
    return {
        "requests": len(rows),
        "by_role": dict(by_role),
        "decisions": dict(decisions),
        "gate": dict(gates),
        "latency_ms": {"p50": round(statistics.median(totals), 1), "p95": round(q[18], 1)},
        "tokens": sum(r["tokens_in"] + r["tokens_out"] for r in rows),
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "redacted_answers": sum(1 for r in rows if r["redactions"]),
    }
