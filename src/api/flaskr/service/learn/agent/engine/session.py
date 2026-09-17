"""Session state and the store protocol hosts implement to persist it."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from .interaction import InteractionSpec
from .script import ScriptBundle


@dataclass
class PendingInteraction:
    """An interaction the model raised and the learner has not answered yet."""

    tool_call_id: str
    spec: InteractionSpec


@dataclass
class Session:
    """Everything that changes as a lesson is taught: history, memory, pending questions."""

    script: ScriptBundle
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str | None = None
    listen_mode: bool = False
    messages: list[ModelMessage] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)  # session scope
    user_memory: dict[str, Any] = field(default_factory=dict)  # snapshot of user scope
    pending: list[PendingInteraction] = field(default_factory=list)
    # Answers collected for this turn's deferred calls, keyed by tool_call_id. A turn can raise
    # several interactions at once; the host answers them one at a time, and they are only handed
    # back to the model together, because pydantic-ai requires a result for every deferred call.
    answers: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)
    turn: int = 0
    finished: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def started(self) -> bool:
        """Report whether the lesson has run at least one turn."""
        return bool(self.messages)

    def all_memory(self) -> dict[str, Any]:
        """Merge user-scoped memory with this session's own, session winning."""
        return {**self.user_memory, **self.memory}

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready form of the session."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "listen_mode": self.listen_mode,
            "script": self.script.to_dict(),
            "messages": json.loads(ModelMessagesTypeAdapter.dump_json(self.messages)),
            "memory": self.memory,
            "user_memory": self.user_memory,
            "pending": [
                {"tool_call_id": p.tool_call_id, "spec": p.spec.model_dump(mode="json")}
                for p in self.pending
            ],
            "answers": self.answers,
            "usage": self.usage,
            "turn": self.turn,
            "finished": self.finished,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Session:
        """Rebuild a session from its JSON form."""
        return cls(
            script=ScriptBundle.from_dict(d["script"]),
            id=d["id"],
            user_id=d.get("user_id"),
            listen_mode=bool(d.get("listen_mode", False)),
            messages=list(
                ModelMessagesTypeAdapter.validate_python(d.get("messages") or [])
            ),
            memory=dict(d.get("memory") or {}),
            user_memory=dict(d.get("user_memory") or {}),
            pending=[
                PendingInteraction(
                    p["tool_call_id"], InteractionSpec.model_validate(p["spec"])
                )
                for p in d.get("pending") or []
            ],
            answers=dict(d.get("answers") or {}),
            usage=dict(d.get("usage") or {}),
            turn=int(d.get("turn", 0)),
            finished=bool(d.get("finished", False)),
            created_at=d.get("created_at") or datetime.now(UTC).isoformat(),
            updated_at=d.get("updated_at") or datetime.now(UTC).isoformat(),
        )

    def dumps(self) -> str:
        """Serialize the session to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def loads(cls, s: str | bytes) -> Session:
        """Rebuild a session from a JSON string."""
        return cls.from_dict(json.loads(s))


class SessionStore(Protocol):
    """Where sessions are kept between turns."""

    async def load(self, session_id: str) -> Session | None:
        """Return the stored session with this id, or None."""

    async def save(self, session: Session) -> None:
        """Store the session, replacing any earlier copy."""


class InMemorySessionStore:
    """A session store that lasts as long as the process. For tests and demos."""

    def __init__(self) -> None:
        """Start empty."""
        self._data: dict[str, str] = {}

    async def load(self, session_id: str) -> Session | None:
        """Return the stored session with this id, or None."""
        raw = self._data.get(session_id)
        return Session.loads(raw) if raw else None

    async def save(self, session: Session) -> None:
        """Store the session, replacing any earlier copy."""
        session.updated_at = datetime.now(UTC).isoformat()
        self._data[session.id] = session.dumps()


class SQLiteSessionStore:
    """Reference implementation on the standard library; one JSON document per session."""

    def __init__(self, path: str = ":memory:") -> None:
        """Open (or create) the SQLite file the sessions live in."""
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT, "
            "updated_at TEXT, data TEXT NOT NULL)"
        )
        self._conn.commit()

    async def load(self, session_id: str) -> Session | None:
        """Return the stored session with this id, or None."""
        row = self._conn.execute(
            "SELECT data FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return Session.loads(row[0]) if row else None

    async def save(self, session: Session) -> None:
        """Store the session, replacing any earlier copy."""
        session.updated_at = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO sessions (id, user_id, updated_at, data) VALUES (?, ?, ?, ?)",
            (session.id, session.user_id, session.updated_at, session.dumps()),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()
