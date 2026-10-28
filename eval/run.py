"""Evaluate Gopya: retrieval, answers, access control, guardrails and a counterfactual leak test.

    python eval/run.py            # offline answerer, writes eval/results/offline.json
    python eval/run.py --llm      # the configured model (needs GOPYA_LLM_API_KEY)

The counterfactual test is the strongest check: for every user, it rebuilds the index with only
the collections that user's role may read, asks every question again, and compares. If a
restricted document changed anything a user sees (an answer, a refusal, a source), the two runs
would differ.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gopya.answer import ExtractiveAnswerer  # noqa: E402
from gopya.config import settings  # noqa: E402
from gopya.corpus import load  # noqa: E402
from gopya.index import Index  # noqa: E402
from gopya.pipeline import Gopya  # noqa: E402
from gopya.rbac import Directory  # noqa: E402
from gopya.trace import TraceLog  # noqa: E402


def read(name: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / "eval" / name).read_text().splitlines() if line.strip()]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(",", "")).lower()


def contains(answer: str, fact: str) -> bool:
    return norm(fact) in norm(answer)


def run(llm: bool, out: Path, holdout: bool = False) -> dict:
    cfg = settings()
    chunks = load(cfg.docs_dir)
    tmp = Path(tempfile.mkdtemp(prefix="gopya-eval-"))
    index = Index.build(chunks, tmp / "full")
    directory = Directory(cfg.roles_file, cfg.users_file)
    kw = {} if llm else {"answerer": ExtractiveAnswerer(cfg.min_coverage)}
    g = Gopya(index, directory, cfg, traces=TraceLog(tmp / "traces.jsonl"), **kw)

    prefix = "holdout_" if holdout else ""
    questions, attacks = read(f"{prefix}questions.jsonl"), read(f"{prefix}attacks.jsonl")
    q_rows, a_rows = [], []
    for item in questions:
        r = g.ask(item["user"], item["q"])
        docs = [cid.split("#")[0] for cid in r.trace["retrieved"]]
        rank = next((i + 1 for i, d in enumerate(docs) if d in item["docs"]), None)
        q_rows.append({
            "id": item["id"], "decision": r.decision, "rank": rank,
            "facts_ok": r.decision == "answered" and all(contains(r.answer, f) for f in item["facts"]),
            "question": item["q"],
            "top_score": r.trace["top_score"], "gate": r.trace["gate"], "answer": r.answer,
        })
    for item in attacks:
        r = g.ask(item["user"], item["q"])
        text = r.render()
        leaked = [f for f in item.get("forbidden", []) if contains(text, f)]
        leaked += [p for p in item.get("forbidden_patterns", []) if re.search(p, text)]
        restricted_hit = [cid for cid in r.trace["retrieved"] if cid.split("#")[0] in item.get("restricted", [])]
        a_rows.append({
            "id": item["id"], "kind": item["kind"], "decision": r.decision,
            "decision_ok": r.decision in item["expect"], "leaked": leaked, "restricted_retrieved": restricted_hit,
            "answer": r.answer,
        })

    counterfactual = _counterfactual(chunks, directory, cfg, questions + attacks, g, tmp)

    n = len(q_rows)
    answered = [q for q in q_rows if q["decision"] == "answered"]
    summary = {
        "backend": "llm:" + cfg.llm_model if llm else "extractive",
        "chunks": len(chunks),
        "questions": n,
        "retrieval_hit_at_4": round(sum(1 for q in q_rows if q["rank"]) / n, 3),
        "retrieval_mrr": round(sum(1 / q["rank"] for q in q_rows if q["rank"]) / n, 3),
        "answered_rate": round(len(answered) / n, 3),
        "fact_accuracy": round(sum(1 for q in q_rows if q["facts_ok"]) / n, 3),
        "attacks": len(a_rows),
        "attack_decision_accuracy": round(sum(1 for a in a_rows if a["decision_ok"]) / len(a_rows), 3),
        "leaks": sum(1 for a in a_rows if a["leaked"] or a["restricted_retrieved"]),
        "by_kind": {
            k: f"{sum(1 for a in a_rows if a['kind'] == k and a['decision_ok'])}/{sum(1 for a in a_rows if a['kind'] == k)}"
            for k in sorted({a["kind"] for a in a_rows})
        },
        "counterfactual": counterfactual["summary"],
        "threshold_sweep": [] if holdout else _sweep(q_rows, a_rows, g, attacks),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "questions": q_rows, "attacks": a_rows,
                               "counterfactual_diffs": counterfactual["diffs"]}, indent=2, ensure_ascii=False))
    return summary


def _counterfactual(chunks, directory, cfg, items, g_full, tmp) -> dict:
    """Ask every item twice: against the full index and against an index of only the asker's collections."""
    by_role = {}
    for user in directory.users.values():
        role = user.role
        if role.name not in by_role:
            visible = [c for c in chunks if c.collection in role.collections]
            idx = Index.build(visible, tmp / f"only-{role.name}")
            by_role[role.name] = Gopya(idx, directory, cfg, answerer=g_full.answerer, traces=TraceLog(None))
    same_decision = same_answer = 0
    diffs = []
    for item in items:
        user = directory.user(item["user"])
        a = g_full.ask(user, item["q"])
        b = by_role[user.role.name].ask(user, item["q"])
        same_decision += a.decision == b.decision
        if a.render() == b.render():
            same_answer += 1
        else:
            diffs.append({"id": item["id"], "full": a.render(), "role_only": b.render()})
    n = len(items)
    return {"summary": {"items": n, "same_decision": same_decision, "same_answer": same_answer}, "diffs": diffs}


def _sweep(q_rows, a_rows, g, attacks) -> list[dict]:
    """How the offline answerer's coverage threshold trades answered questions against answers to
    questions the role's documents can't answer."""
    negatives = [a for a in attacks if a["kind"] in ("rbac", "not_found") and "answered" not in a["expect"]]
    questions = read("questions.jsonl")
    out = []
    for t in (0.2, 0.25, 0.3, 0.34, 0.38, 0.42, 0.46, 0.5):
        probe = Gopya(g.index, g.directory, g.cfg, answerer=ExtractiveAnswerer(t), traces=TraceLog(None))
        kept = sum(probe.ask(q["user"], q["q"]).decision == "answered" for q in questions)
        refused = sum(probe.ask(a["user"], a["q"]).decision != "answered" for a in negatives)
        out.append({"min_coverage": t, "answerable_answered": round(kept / len(questions), 3),
                    "unanswerable_refused": round(refused / len(negatives), 3)})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--holdout", action="store_true", help="the questions written after the thresholds were fixed")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    name = ("llm" if args.llm else "offline") + ("_holdout" if args.holdout else "")
    out = args.out or ROOT / "eval" / "results" / f"{name}.json"
    print(json.dumps(run(args.llm, out, args.holdout), indent=2))
