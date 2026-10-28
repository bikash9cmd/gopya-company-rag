"""Load the knowledge base and cut it into chunks that carry their access metadata.

Each top-level folder under the docs directory is one collection ("finance", "hr", ...). The
collection is stamped on every chunk at ingestion, and retrieval filters on it, so access is
decided by where a document lives, never by what it says.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .text import npr, unwrap

MAX_CHARS = 900


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    collection: str
    title: str
    section: str
    text: str
    source: str
    updated: str = ""
    has_pii: bool = False
    meta: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def header(self) -> str:
        return f"{self.title} > {self.section}" if self.section else self.title


def load(docs_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        collection = path.relative_to(docs_dir).parts[0]
        if path.suffix == ".md":
            chunks.extend(_markdown(path, collection, docs_dir))
        elif path.suffix == ".csv":
            chunks.extend(_csv(path, collection, docs_dir))
        elif path.suffix == ".pdf":
            chunks.extend(_pdf(path, collection, docs_dir))
    ids = [c.id for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate chunk ids")
    return chunks


def _doc_id(path: Path, docs_dir: Path) -> str:
    return path.relative_to(docs_dir).with_suffix("").as_posix()


def _chunk_id(doc_id: str, n: int) -> str:
    return f"{doc_id}#{n}"


# --- markdown -------------------------------------------------------------------------------

_FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _markdown(path: Path, collection: str, docs_dir: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    m = _FRONT.match(raw)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        raw = raw[m.end():]
    if meta.get("dept") and meta["dept"] != collection:
        # The folder is the access boundary. A front-matter label that disagrees is a filing
        # mistake that would otherwise be silently ignored.
        raise ValueError(f"{path}: dept '{meta['dept']}' does not match folder '{collection}'")

    doc_id = _doc_id(path, docs_dir)
    title = meta.get("title") or path.stem.replace("-", " ").capitalize()
    out: list[Chunk] = []
    for section, body in _sections(raw):
        body = _tables_to_sentences(unwrap(body)).strip()
        if not body:
            continue
        for piece in _split(body):
            out.append(
                Chunk(
                    id=_chunk_id(doc_id, len(out)),
                    doc_id=doc_id,
                    collection=collection,
                    title=title,
                    section=section,
                    text=piece,
                    source=path.relative_to(docs_dir).as_posix(),
                    updated=meta.get("updated", ""),
                    meta={"owner": meta.get("owner", "")},
                )
            )
    return out


def _sections(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    current, buf = "", []
    for line in text.splitlines():
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            if buf:
                out.append((current, "\n".join(buf)))
            current, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if buf:
        out.append((current, "\n".join(buf)))
    return out


def _tables_to_sentences(body: str) -> str:
    """Turn markdown table rows into "Header: value; Header: value." lines.

    A bare row like "| Up to Rs 50,000 | Head of department |" means nothing once it is cut out of
    its table. With the headers inlined, every row survives chunking and reads as a fact.
    """
    lines = body.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < len(lines) and set(lines[i + 1].strip()) <= set("|-: "):
            headers = [h.strip() for h in line.strip("|").split("|")]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("; ".join(f"{h}: {c}" for h, c in zip(headers, cells)) + ".")
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _split(body: str) -> list[str]:
    if len(body) <= MAX_CHARS:
        return [body]
    pieces, buf = [], ""
    for para in re.split(r"\n\s*\n|\n(?=\d+\. |- )", body):
        para = para.strip()
        if not para:
            continue
        if buf and len(buf) + len(para) > MAX_CHARS:
            pieces.append(buf)
            buf = para
        else:
            buf = f"{buf}\n{para}" if buf else para
    if buf:
        pieces.append(buf)
    return pieces


# --- csv ------------------------------------------------------------------------------------

PII_COLUMNS = {"citizenship_no", "mobile", "bank_account", "pan_no", "email_personal"}


def _csv(path: Path, collection: str, docs_dir: Path) -> list[Chunk]:
    doc_id = _doc_id(path, docs_dir)
    title = path.stem.replace("-", " ").replace("_", " ").capitalize()
    out: list[Chunk] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("name") or row.get(next(iter(row)))
            parts = []
            for key, value in row.items():
                label = key.replace("_npr", "").replace("_", " ")
                if key.endswith("_npr") and value.isdigit():
                    value = npr(int(value))
                parts.append(f"{label}: {value}")
            out.append(
                Chunk(
                    id=_chunk_id(doc_id, len(out)),
                    doc_id=doc_id,
                    collection=collection,
                    title=title,
                    section=name,
                    text=f"Employee record for {name}. " + "; ".join(parts) + ".",
                    source=path.relative_to(docs_dir).as_posix(),
                    has_pii=bool(PII_COLUMNS & set(row)),
                )
            )
    return out


# --- pdf ------------------------------------------------------------------------------------

_PDF_HEADING = re.compile(r"^(?:\d+\.\s+\S.*|Present|Next meeting)$")


def _pdf(path: Path, collection: str, docs_dir: Path) -> list[Chunk]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = (reader.metadata.title if reader.metadata else None) or (lines[0] if lines else path.stem)
    doc_id = _doc_id(path, docs_dir)

    sections: list[tuple[str, list[str]]] = []
    for line in lines[1:]:
        if _PDF_HEADING.match(line) and len(line) < 70:
            sections.append((line, []))
        elif sections:
            sections[-1][1].append(line)
    out: list[Chunk] = []
    for heading, body in sections:
        joined = " ".join(body)
        for piece in _split(joined):
            out.append(
                Chunk(
                    id=_chunk_id(doc_id, len(out)),
                    doc_id=doc_id,
                    collection=collection,
                    title=lines[0] if lines else title,
                    section=heading,
                    text=piece,
                    source=path.relative_to(docs_dir).as_posix(),
                )
            )
    return out


def fingerprint(chunks: list[Chunk]) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(f"{c.id}|{c.collection}|{c.text}".encode())
    return h.hexdigest()[:16]
