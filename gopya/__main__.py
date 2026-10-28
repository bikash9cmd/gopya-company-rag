"""Command line: ingest, ask, chat, stats, serve."""

from __future__ import annotations

import argparse
import json
import sys

from .config import settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="gopya", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest", help="parse data/docs and build the vector index")
    a = sub.add_parser("ask", help="ask one question as a user")
    a.add_argument("--as", dest="user", required=True, help="user id from data/users.toml")
    a.add_argument("question")
    a.add_argument("--trace", action="store_true", help="also print the request trace")
    c = sub.add_parser("chat", help="interactive chat as a user")
    c.add_argument("--as", dest="user", required=True)
    sub.add_parser("stats", help="summarise var/traces.jsonl")
    s = sub.add_parser("serve", help="run the HTTP API")
    s.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    cfg = settings()

    if args.cmd == "ingest":
        from .corpus import load
        from .index import Index

        chunks = load(cfg.docs_dir)
        Index.build(chunks, cfg.index_dir)
        by = {}
        for ch in chunks:
            by[ch.collection] = by.get(ch.collection, 0) + 1
        print(f"indexed {len(chunks)} chunks into {cfg.index_dir}: " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
        return 0

    if args.cmd in ("ask", "chat"):
        from .pipeline import Gopya

        g = Gopya.open(cfg)
        user = g.directory.user(args.user)
        if args.cmd == "ask":
            r = g.ask(user, args.question)
            print(r.render())
            if args.trace:
                print("\n" + json.dumps(r.trace, indent=2, ensure_ascii=False))
            return 0
        print(f"Signed in as {user.name} ({user.role.name}). Ctrl-D to quit.")
        for line in sys.stdin:
            if line.strip():
                print(g.ask(user, line).render() + "\n")
        return 0

    if args.cmd == "stats":
        from .trace import summarise

        print(json.dumps(summarise(cfg.trace_file), indent=2))
        return 0

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("gopya.api:app", host="0.0.0.0", port=args.port)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
