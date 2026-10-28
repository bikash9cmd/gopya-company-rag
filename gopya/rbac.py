"""Roles, users and what each role may read."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Role:
    name: str
    collections: frozenset[str]
    pii: bool
    description: str = ""


@dataclass(frozen=True)
class User:
    id: str
    name: str
    role: Role


class AccessError(Exception):
    pass


class Directory:
    def __init__(self, roles_file: Path, users_file: Path):
        raw_roles = tomllib.loads(roles_file.read_text())["roles"]
        self.roles = {
            name: Role(name, frozenset(r["collections"]), bool(r.get("pii", False)), r.get("description", ""))
            for name, r in raw_roles.items()
        }
        raw_users = tomllib.loads(users_file.read_text())["users"]
        self.users: dict[str, User] = {}
        self._tokens: dict[str, str] = {}
        for uid, u in raw_users.items():
            if u["role"] not in self.roles:
                raise ValueError(f"user {uid} has unknown role {u['role']}")
            self.users[uid] = User(uid, u["name"], self.roles[u["role"]])
            self._tokens[u["token"]] = uid

    def user(self, user_id: str) -> User:
        try:
            return self.users[user_id]
        except KeyError:
            raise AccessError(f"unknown user {user_id!r}") from None

    def by_token(self, token: str) -> User:
        uid = self._tokens.get(token)
        if uid is None:
            raise AccessError("invalid token")
        return self.users[uid]
