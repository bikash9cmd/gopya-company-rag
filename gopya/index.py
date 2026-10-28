"""Hybrid retrieval (dense vectors in Chroma + BM25) with the role filter applied inside both.

The access check is not a post-filter on results. Chroma is queried with
where={"collection": {"$in": allowed}}, and BM25 only scores chunks from allowed collections, so
a restricted chunk is never ranked, never returned and never shown to the model. Every number
that later decisions use (scores, "not found", "out of scope") is computed from allowed chunks
only, which is what makes the answer for a restricted question indistinguishable from the answer
for a question about something that doesn't exist.
"""

from __future__ import annotations

import json
import math
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import chromadb

from .corpus import Chunk, fingerprint
from .embed import LsaEmbedder
from .text import tokens

COLLECTION = "gopya"


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float  # fused relevance in [0, 1]
    dense: float
    bm25: float
    coverage: float = 0.0  # IDF-weighted share of the question's terms found in this chunk


class Index:
    def __init__(self, chunks: list[Chunk], embedder: LsaEmbedder, store: chromadb.api.ClientAPI):
        self.chunks = {c.id: c for c in chunks}
        self.embedder = embedder
        self.col = store.get_collection(COLLECTION)
        self._bm25 = _Bm25([(c.id, tokens(f"{c.header} {c.text}")) for c in chunks])

    # -- building --------------------------------------------------------------------------

    @classmethod
    def build(cls, chunks: list[Chunk], index_dir: Path) -> "Index":
        if index_dir.exists():
            shutil.rmtree(index_dir)
        index_dir.mkdir(parents=True)
        texts = [f"{c.header}. {c.text}" for c in chunks]
        embedder = LsaEmbedder().fit(texts)
        store = chromadb.PersistentClient(path=str(index_dir / "chroma"))
        col = store.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        col.add(
            ids=[c.id for c in chunks],
            embeddings=embedder.embed(texts).tolist(),
            documents=[c.text for c in chunks],
            metadatas=[{"collection": c.collection, "doc_id": c.doc_id, "has_pii": c.has_pii} for c in chunks],
        )
        embedder.save(index_dir / "embedder.pkl")
        (index_dir / "chunks.json").write_text(
            json.dumps([c.__dict__ for c in chunks], ensure_ascii=False, indent=0)
        )
        (index_dir / "manifest.json").write_text(
            json.dumps({"chunks": len(chunks), "fingerprint": fingerprint(chunks), "embedder": embedder.name})
        )
        return cls(chunks, embedder, store)

    @classmethod
    def open(cls, index_dir: Path) -> "Index":
        if not (index_dir / "manifest.json").exists():
            raise FileNotFoundError(f"no index at {index_dir}: run `python -m gopya ingest` first")
        chunks = [Chunk(**d) for d in json.loads((index_dir / "chunks.json").read_text())]
        embedder = LsaEmbedder.load(index_dir / "embedder.pkl")
        store = chromadb.PersistentClient(path=str(index_dir / "chroma"))
        return cls(chunks, embedder, store)

    # -- querying --------------------------------------------------------------------------

    def term_weights(self, allowed: frozenset[str]) -> tuple[dict[str, float], float]:
        """IDF over the role's chunks, and the weight given to a term the role has never seen."""
        ids = frozenset(cid for cid, c in self.chunks.items() if c.collection in allowed)
        idf, _ = self._bm25._for(ids)
        return idf, math.log(1 + (len(ids) + 0.5) / 0.5)

    def search(self, query: str, allowed: frozenset[str], k: int = 4) -> list[Hit]:
        if not allowed:
            return []
        allowed_list = sorted(allowed)
        where = {"collection": {"$in": allowed_list}} if len(allowed_list) > 1 else {"collection": allowed_list[0]}
        n_allowed = sum(1 for c in self.chunks.values() if c.collection in allowed)
        pool = min(max(k * 4, 12), n_allowed)
        if pool == 0:
            return []

        res = self.col.query(
            query_embeddings=self.embedder.embed([query]).tolist(), n_results=pool, where=where,
            include=["distances", "metadatas"],
        )
        dense = {}
        for cid, dist, md in zip(res["ids"][0], res["distances"][0], res["metadatas"][0]):
            if md["collection"] not in allowed:  # defence in depth: the store already filtered
                raise AssertionError(f"vector store returned {cid} outside the role's collections")
            dense[cid] = max(0.0, 1.0 - dist)

        q_tokens = tokens(query)
        keep = lambda cid: self.chunks[cid].collection in allowed  # noqa: E731
        bm = self._bm25.scores(q_tokens, keep)
        top_bm = sorted(bm.items(), key=lambda kv: -kv[1])[:pool]
        bm_max = top_bm[0][1] if top_bm and top_bm[0][1] > 0 else 1.0

        # Reciprocal rank fusion decides the order; the reported score blends the two signals so
        # a threshold can say "nothing relevant here".
        rrf: Counter[str] = Counter()
        for rank, cid in enumerate(sorted(dense, key=lambda c: -dense[c])):
            rrf[cid] += 1 / (60 + rank)
        for rank, (cid, s) in enumerate(top_bm):
            if s > 0:
                rrf[cid] += 1 / (60 + rank)
        hits = []
        for cid, _ in rrf.most_common(k):
            d = dense.get(cid, 0.0)
            b = bm.get(cid, 0.0) / bm_max
            # BM25 normalised by the best allowed hit says nothing on its own about whether the
            # best hit is any good, so it is damped by the absolute BM25 score.
            b_abs = 1 - math.exp(-bm.get(cid, 0.0) / 6)
            cov = self._bm25.coverage(q_tokens, cid, keep)
            hits.append(Hit(self.chunks[cid], round(0.5 * d + 0.5 * b * b_abs, 4), round(d, 4), round(b, 4), round(cov, 4)))
        return hits


class _Bm25:
    def __init__(self, docs: list[tuple[str, list[str]]], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = {cid: Counter(toks) for cid, toks in docs}
        self.lens = {cid: len(toks) for cid, toks in docs}
        self._stats: dict[frozenset[str], tuple[dict[str, float], float]] = {}

    def _for(self, ids: frozenset[str]) -> tuple[dict[str, float], float]:
        # IDF and average length are computed over the chunks the role may read, not the whole
        # corpus, so a restricted document can't shift the scores of the documents a role sees.
        if ids not in self._stats:
            df: Counter[str] = Counter()
            for cid in ids:
                df.update(self.docs[cid].keys())
            n = len(ids)
            idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
            avg = sum(self.lens[c] for c in ids) / max(1, n)
            self._stats[ids] = (idf, avg)
        return self._stats[ids]

    def coverage(self, q: list[str], cid: str, keep) -> float:
        """Share of the question's IDF mass that appears in the chunk. Terms the role's corpus has
        never seen count as missing at the highest IDF, so a question about something absent from
        the role's documents scores low even when a few common words match."""
        ids = frozenset(c for c in self.docs if keep(c))
        idf, _ = self._for(ids)
        unseen = math.log(1 + (len(ids) + 0.5) / 0.5)
        terms = set(q)
        if not terms:
            return 0.0
        total = sum(idf.get(t, unseen) for t in terms)
        found = sum(idf[t] for t in terms if t in self.docs[cid])
        return found / total if total else 0.0

    def scores(self, q: list[str], keep) -> dict[str, float]:
        ids = frozenset(cid for cid in self.docs if keep(cid))
        idf, avg = self._for(ids)
        out = {}
        for cid in ids:
            counts = self.docs[cid]
            s = 0.0
            for t in set(q):
                tf = counts.get(t)
                if tf:
                    s += idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * self.lens[cid] / avg))
            if s:
                out[cid] = s
        return out
