"""HTTP API. The caller's role comes from the bearer token, never from the request body."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .pipeline import Gopya
from .rbac import AccessError, User

app = FastAPI(title="Gopya", version="0.1.0")


@lru_cache(maxsize=1)
def engine() -> Gopya:
    return Gopya.open()


def current_user(authorization: str = Header(default="")) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return engine().directory.by_token(token)
    except AccessError:
        raise HTTPException(status_code=401, detail="invalid or missing token") from None


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"user": user.id, "name": user.name, "role": user.role.name}


@app.post("/ask")
def ask(body: Ask, user: User = Depends(current_user)) -> dict:
    r = engine().ask(user, body.question)
    return {
        "answer": r.answer,
        "decision": r.decision,
        "sources": [s.__dict__ for s in r.sources],
        "latency_ms": r.trace["ms"]["total"],
    }
