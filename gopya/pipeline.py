"""The request path: guard the question, retrieve within the role, answer, check, trace."""

from __future__ import annotations

from dataclasses import dataclass, field

from .answer import ExtractiveAnswerer, LlmAnswerer
from .config import Settings, settings as load_settings
from .guards import REFUSALS, check_input, redact
from .index import Index
from .llm import ChatClient
from .rbac import Directory, User
from .trace import Trace, TraceLog, cost_usd


@dataclass
class Source:
    n: int
    title: str
    section: str
    path: str
    updated: str

    def __str__(self) -> str:
        where = f"{self.title} > {self.section}" if self.section else self.title
        when = f", updated {self.updated}" if self.updated else ""
        return f"[{self.n}] {where} ({self.path}{when})"


@dataclass
class Response:
    answer: str
    decision: str  # "answered", "not_found", "injection", "out_of_scope", "empty", "too_long"
    sources: list[Source] = field(default_factory=list)
    trace: dict = field(default_factory=dict)

    def render(self) -> str:
        if not self.sources:
            return self.answer
        return self.answer + "\n\nSources:\n" + "\n".join(str(s) for s in self.sources)


class Gopya:
    def __init__(self, index: Index, directory: Directory, cfg: Settings | None = None,
                 answerer=None, traces: TraceLog | None = None):
        self.cfg = cfg or load_settings()
        self.index = index
        self.directory = directory
        self.traces = traces if traces is not None else TraceLog(self.cfg.trace_file)
        self.extractive = ExtractiveAnswerer(self.cfg.min_coverage)
        if answerer is not None:
            self.answerer = answerer
        elif self.cfg.llm_enabled:
            client = ChatClient(self.cfg.llm_base_url, self.cfg.llm_api_key, self.cfg.llm_model, self.cfg.llm_timeout_s)
            self.answerer = LlmAnswerer(client, self.extractive)
        else:
            self.answerer = self.extractive

    @classmethod
    def open(cls, cfg: Settings | None = None, **kw) -> "Gopya":
        cfg = cfg or load_settings()
        return cls(Index.open(cfg.index_dir), Directory(cfg.roles_file, cfg.users_file), cfg, **kw)

    def ask(self, user: User | str, question: str) -> Response:
        if isinstance(user, str):
            user = self.directory.user(user)
        role = user.role
        t = Trace(user=user.id, role=role.name, question=question.strip()[:600])

        check = check_input(question)
        t.lap("guard_in")
        if not check.ok:
            return self._finish(t, Response(REFUSALS[check.reason].format(role=role.name), check.reason))

        hits = self.index.search(question, role.collections, self.cfg.top_k)
        t.lap("retrieve")
        t.retrieved = [h.chunk.id for h in hits]
        t.top_score = hits[0].score if hits else 0.0
        if not hits or hits[0].score < self.cfg.min_relevance:
            return self._finish(t, Response(REFUSALS["not_found"], "not_found"))

        contexts = []
        for h in hits:
            text = h.chunk.text
            if not role.pii:
                text, found = redact(text)
                t.redactions.extend(f for f in found if f not in t.redactions)
            contexts.append(text)

        answerer = self.answerer
        if answerer is not self.extractive and self.traces.spent_today(user.id) >= self.cfg.daily_token_budget:
            answerer = self.extractive
            t.gate = "budget"
        draft = answerer.answer(question, hits, contexts, self.index.term_weights(role.collections))
        t.lap("answer")
        t.backend, t.model = draft.backend, draft.model
        t.gate = t.gate or draft.gate
        t.tokens_in, t.tokens_out = draft.tokens_in, draft.tokens_out
        t.cost_usd = cost_usd(self.cfg.prices, draft.model, draft.tokens_in, draft.tokens_out)

        if not draft.text:
            return self._finish(t, Response(REFUSALS["not_found"], "not_found"))

        text = draft.text
        if not role.pii:
            text, _ = redact(text)  # second line of defence on the final answer
        renumber = {old: new for new, old in enumerate(draft.cited, start=1)}
        for old, new in sorted(renumber.items(), key=lambda kv: -kv[0]):
            text = text.replace(f"[{old}]", f"[§{new}]")
        text = text.replace("[§", "[")
        sources = [
            Source(renumber[i], hits[i - 1].chunk.title, hits[i - 1].chunk.section, hits[i - 1].chunk.source,
                   hits[i - 1].chunk.updated)
            for i in draft.cited
        ]
        return self._finish(t, Response(text, "answered", sources))

    def _finish(self, t: Trace, r: Response) -> Response:
        t.decision = r.decision
        rec = t.finish()
        self.traces.write(rec)
        r.trace = rec
        return r
