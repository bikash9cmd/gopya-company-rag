"""Small text helpers shared by retrieval, guards and the answerer."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
STOPWORDS = frozenset(
    """a an and are as at be by can do does for from has have how i in is it its me my of on or
    our please tell that the their there this to us was we what when where which who why will with
    you your about any get much many should would could
    kati ke ko ka ki le lai ma cha chha chhan ho hun garne garnu pauchha paincha kahile kasari kun""".split()
    # The second line is Romanized Nepali function words ("kati din" = "how many days").
)

# Canonical forms so a question and a document that say the same thing share tokens. The
# Romanized Nepali entries let staff ask "sick leave kati din pauchha?" and still match.
CANON = {
    "hire": "recruit", "hiring": "recruit", "recruitment": "recruit", "vacancy": "recruit",
    "wage": "salary", "pay": "salary", "talab": "salary",
    "chhuti": "leave", "bida": "leave", "holiday": "leave",
    "din": "day", "days": "day", "mahina": "month", "barsa": "year", "barsha": "year",
    "kharcha": "expense", "bhatta": "allowance",
}


def tokens(text: str) -> list[str]:
    # "7,000" and "7000" must be the same token, and "1,25,000" the same as "125000".
    out = []
    for t in _TOKEN.findall(text.lower()):
        if t in STOPWORDS:
            continue
        t = _stem(t.replace(",", ""))
        out.append(_CANON.get(t, t))
    return out


def _stem(word: str) -> str:
    # A light suffix stripper: enough to match "approves"/"approval"/"approve" style variants
    # without pulling in a stemmer dependency.
    for suffix in ("ations", "ation", "ings", "ing", "ies", "es", "ed", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            word = word[: -len(suffix)] + ("y" if suffix == "ies" else "")
            break
    if len(word) > 4 and word.endswith("e") and not word[-2].isdigit():
        word = word[:-1]  # "generate" and "generated" both become "generat"
    return word


_CANON = {_stem(k): _stem(v) for k, v in CANON.items()}

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> set[str]:
    """Every number in the text, with thousands separators removed ("1,25,000" -> "125000")."""
    out = set()
    for m in _NUMBER.findall(text):
        n = m.replace(",", "").rstrip(".")
        if n:
            out.add(n.lstrip("0") or "0")
    return out


def npr(amount: int) -> str:
    """Format rupees with Nepali digit grouping: 410000 -> "Rs 4,10,000"."""
    s = str(int(amount))
    if len(s) <= 3:
        return f"Rs {s}"
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "Rs " + ",".join(groups + [tail])


def sentences(text: str) -> list[str]:
    parts = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts.extend(p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line) if p.strip())
    return parts


_BLOCK_START = re.compile(r"^\s*(?:[-*] |\d+\. |\|)")


def unwrap(text: str) -> str:
    """Join hard-wrapped lines into paragraphs, keeping list items and table rows on their own lines."""
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append("")
        elif out and out[-1] and not _BLOCK_START.match(line) and not out[-1].endswith(":"):
            out[-1] = f"{out[-1]} {stripped}"
        else:
            out.append(stripped)
    return "\n".join(out)
