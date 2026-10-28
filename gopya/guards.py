"""Input and output guardrails.

Input: refuse prompt injection and role claims, and questions outside company business.
Output and context: redact personal identity numbers, phone numbers and bank accounts for roles
without PII clearance, before the model sees the context and again on the final answer.

None of these checks look at documents, so none of them can reveal whether a restricted document
exists. Relevance ("is this in your documents?") is decided later, from allowed chunks only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_QUESTION_CHARS = 600

_INJECTION = [
    r"\bignore\b.{0,40}\b(instruction|rule|prompt|previous|above|polic)",
    r"\bdisregard\b.{0,40}\b(instruction|rule|prompt|polic)",
    r"\b(forget|override|bypass)\b.{0,30}\b(rule|instruction|restriction|access|polic|filter|guard)",
    r"\b(system|hidden|developer)\s+prompt\b",
    r"\byou are now\b|\bact as\b|\bpretend (to be|you are)\b|\bdeveloper mode\b|\bjailbreak\b|\bDAN\b",
    r"\b(reveal|print|show|repeat)\b.{0,20}\b(instructions|prompt|context)\b",
    r"\b(i am|i'm|im|this is)\s+(the\s+)?(ceo|cfo|admin|administrator|hr head|head of hr|board member|it admin)\b",
    r"\b(as|with)\s+(an?\s+|the\s+)?(admin|administrator|executive|ceo|cfo)\s+(access|role|permission|rights)\b",
    r"\b(grant|give|elevate|escalate|switch)\b.{0,20}\b(access|role|permission|privilege)",
    r"\b(list|show|dump|export)\b.{0,15}\b(all|every)\b.{0,15}\b(document|file|folder|record|collection)",
    r"\bwhat (documents|files|folders) (exist|are there)\b",
]

# Topics a company knowledge assistant should decline outright, whatever the documents say.
_OUT_OF_SCOPE = [
    r"\b(python|javascript|java|c\+\+|typescript|sql|regex|html|css)\b.{0,40}\b(code|function|script|query|program|write)\b",
    r"\b(write|give|show)\b.{0,15}\b(code|function|program|script)\b",
    r"\b(linked list|binary tree|sort(ing)? algorithm|leetcode|big o)\b",
    r"\b(recipe|cook(ing)?|momo recipe)\b",
    r"\b(poem|song|joke|story|essay|lyrics)\b",
    r"\b(cricket|football|ipl|world cup|movie|film|netflix)\b",
    r"\b(capital of|president of|prime minister of|who won)\b",
    r"\b(weather|horoscope|lottery)\b",
    r"\b(bitcoin|crypto|share price|nepse)\b",
    r"\b(girlfriend|boyfriend|dating)\b",
]

_inj = [re.compile(p, re.I) for p in _INJECTION]
_oos = [re.compile(p, re.I) for p in _OUT_OF_SCOPE]


@dataclass(frozen=True)
class InputCheck:
    ok: bool
    reason: str = ""  # "", "empty", "too_long", "injection", "out_of_scope"
    rule: str = ""


def check_input(question: str) -> InputCheck:
    q = question.strip()
    if not q:
        return InputCheck(False, "empty")
    if len(q) > MAX_QUESTION_CHARS:
        return InputCheck(False, "too_long")
    for pat in _inj:
        if pat.search(q):
            return InputCheck(False, "injection", pat.pattern)
    for pat in _oos:
        if pat.search(q):
            return InputCheck(False, "out_of_scope", pat.pattern)
    return InputCheck(True)


# --- PII ------------------------------------------------------------------------------------

PII_PATTERNS = {
    # Nepali citizenship certificate numbers are district-serial forms like 52-03-76-95319.
    "citizenship_no": re.compile(r"\b\d{1,2}-\d{2}-\d{2}-\d{4,6}\b"),
    "mobile": re.compile(r"(?<!\d)(?:\+?977[- ]?)?9[678]\d{8}(?!\d)"),
    "bank_account": re.compile(r"(?<![\d,.])\d{11,18}(?!\d|[,.]\d)"),
}
REDACTED = "[redacted]"


def redact(text: str) -> tuple[str, list[str]]:
    found = []
    for name, pat in PII_PATTERNS.items():
        if pat.search(text):
            found.append(name)
            text = pat.sub(REDACTED, text)
    return text, found


REFUSALS = {
    "empty": "Please type a question.",
    "too_long": f"Please keep the question under {MAX_QUESTION_CHARS} characters.",
    "injection": (
        "I can't change my rules or your access. I answer using the role you signed in with ({role}). "
        "If you need access to more documents, ask your head of department."
    ),
    "out_of_scope": "I only answer questions about Kanchan Hydro's own policies, operations and records.",
    "not_found": (
        "I couldn't find that in the documents you have access to. "
        "Try rephrasing, or ask the owner of the relevant policy."
    ),
    "budget": "You've reached today's assistant limit. Answers now come from the offline search only.",
}
