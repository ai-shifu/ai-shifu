"""Session state and the store protocol hosts implement to persist it."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ToolCallPart,
    ToolReturnPart,
)

from .interaction import DEFAULT_CONFIRM_LABEL, InteractionSpec
from .script import ScriptBundle


def answer_fingerprint(value: object) -> str | None:
    """Identify an exact answer copy without duplicating the learner's long value."""
    if not isinstance(value, str):
        return None
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True).encode("ascii")
    ).hexdigest()


@dataclass
class PendingInteraction:
    """An interaction the model raised and the learner has not answered yet."""

    tool_call_id: str
    spec: InteractionSpec


def _restored_spec(stored: dict[str, Any]) -> InteractionSpec:
    """Rebuild a pending question from a stored session.

    Sessions written before the engine recorded who named a confirm's button carry no such
    field, and a learner mid-lesson at the moment that change ships would get the English
    default back on a button the host had been translating. A stored confirm carrying exactly
    the engine's own default is taken to be the engine's, which is what it was.

    Only for what is missing from the stored form. A session written since records the answer
    and is believed. Removable once no session predating the field can still be open.
    """
    spec = InteractionSpec.model_validate(stored)
    if (
        "labelled_by_engine" not in stored
        and spec.type == "confirm"
        and spec.options
        and spec.options[0].display == DEFAULT_CONFIRM_LABEL
        and spec.options[0].value == "continue"
    ):
        spec.labelled_by_engine = True
    return spec


@dataclass
class Session:
    """Everything that changes as a lesson is taught: history, memory, pending questions."""

    script: ScriptBundle
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str | None = None
    listen_mode: bool = False
    messages: list[ModelMessage] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)  # session scope
    answer_hashes: dict[str, str] = field(default_factory=dict)
    user_memory: dict[str, Any] = field(default_factory=dict)  # snapshot of user scope
    # Exact source values for initial host substitutions; None identifies legacy sessions.
    initial_variables: dict[str, Any] | None = None
    pending: list[PendingInteraction] = field(default_factory=list)
    # Answers collected for this turn's deferred calls, keyed by tool_call_id. A turn can raise
    # several interactions at once; the host answers them one at a time, and they are only handed
    # back to the model together, because pydantic-ai requires a result for every deferred call.
    answers: dict[str, Any] = field(default_factory=dict)
    # Accepted free text awaiting a model response; never inferred from choice values/history.
    request_inputs: list[str] = field(default_factory=list)
    # Derived historical overviews only; never learner memory or instruction authority.
    teaching_summaries: dict[str, str] = field(default_factory=dict)
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

    def answered_memory_keys(self) -> frozenset[str]:
        """Identify current copies still owned by an accepted named answer."""
        return frozenset(
            key
            for key, digest in self.answer_hashes.items()
            if isinstance(digest, str)
            and key in self.memory
            and answer_fingerprint(self.memory[key]) == digest
        )

    def record_answer(self, key: str, value: str) -> None:
        """Replace a named-answer copy and its ownership fingerprint together."""
        digest = answer_fingerprint(value)
        if digest is None:
            message = "named answers must be strings"
            raise TypeError(message)
        self.memory[key] = value
        self.answer_hashes[key] = digest

    def _legacy_answer_hashes(self) -> dict[str, str]:
        """Recover matching answer copies from old persisted host results.

        Pending deferred results already live in `answers`; completed results live in
        typed history. Only copies matching that evidence can acquire a fingerprint.
        Ambiguous calls, failed returns and unasked/empty answers establish no acceptance.
        """
        counts = Counter(
            part.tool_call_id
            for message in self.messages
            for part in message.parts
            if isinstance(part, ToolCallPart)
        )
        returns = Counter(
            part.tool_call_id
            for message in self.messages
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        )
        calls: dict[str, tuple[str, str, str | None]] = {}
        accepted: dict[str, str] = {}

        def accept(call_id: str, content: object) -> None:
            """Recognize a nonempty host answer for a unique named interaction."""
            if (
                call_id not in calls
                or returns[call_id] > 1
                or not isinstance(content, str)
            ):
                return
            for prefix in ("Learner wrote: ", "Learner chose: "):
                if content.startswith(prefix) and content[len(prefix) :].strip():
                    name, key, _ = calls[call_id]
                    if name == "interact":
                        value = content[len(prefix) :]
                        if prefix == "Learner chose: " and value != self.memory.get(
                            key
                        ):
                            value = value.replace("; and wrote: ", "; ", 1)
                        accepted[key] = value
            name, key, value = calls[call_id]
            if name == "remember" and value is not None:
                if content == f"remembered {key} (session)":
                    accepted.pop(key, None)
                elif content == f"remembered {key} (user)" and key in accepted:
                    accepted[key] = value

        for message in self.messages:
            for part in message.parts:
                if (
                    isinstance(part, ToolCallPart)
                    and part.tool_name in {"interact", "remember"}
                    and counts[part.tool_call_id] == 1
                ):
                    try:
                        args = part.args_as_dict()
                    except (AssertionError, TypeError, ValueError):
                        continue
                    key = (
                        args.get("variable" if part.tool_name == "interact" else "key")
                        if isinstance(args, dict)
                        else None
                    )
                    if isinstance(key, str) and key.strip():
                        value = args.get("value")
                        calls[part.tool_call_id] = (
                            part.tool_name,
                            key,
                            value if isinstance(value, str) else None,
                        )
                elif (
                    isinstance(part, ToolReturnPart)
                    and part.tool_name in {"interact", "remember"}
                    and part.outcome == "success"
                    and part.tool_call_id in calls
                    and part.tool_name == calls[part.tool_call_id][0]
                ):
                    accept(part.tool_call_id, part.content)
        for call_id, content in self.answers.items():
            if call_id in calls and calls[call_id][0] == "interact":
                accept(call_id, content)
        return {
            key: answer_fingerprint(value)
            for key, value in accepted.items()
            if key in self.memory and self.memory[key] == value
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready form of the session."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "listen_mode": self.listen_mode,
            "script": self.script.to_dict(),
            "messages": json.loads(ModelMessagesTypeAdapter.dump_json(self.messages)),
            "memory": self.memory,
            "answer_hashes": dict(self.answer_hashes),
            "user_memory": self.user_memory,
            "initial_variables": self.initial_variables,
            "pending": [
                {"tool_call_id": p.tool_call_id, "spec": p.spec.model_dump(mode="json")}
                for p in self.pending
            ],
            "answers": self.answers,
            "request_inputs": self.request_inputs,
            "teaching_summaries": self.teaching_summaries,
            "usage": self.usage,
            "turn": self.turn,
            "finished": self.finished,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Session:
        """Rebuild a session from its JSON form."""
        session = cls(
            script=ScriptBundle.from_dict(d["script"]),
            id=d["id"],
            user_id=d.get("user_id"),
            listen_mode=bool(d.get("listen_mode", False)),
            messages=list(
                ModelMessagesTypeAdapter.validate_python(d.get("messages") or [])
            ),
            memory=dict(d.get("memory") or {}),
            answer_hashes=dict(d.get("answer_hashes") or {}),
            user_memory=dict(d.get("user_memory") or {}),
            initial_variables=(
                dict(d["initial_variables"])
                if d.get("initial_variables") is not None
                else None
            ),
            pending=[
                PendingInteraction(p["tool_call_id"], _restored_spec(p["spec"]))
                for p in d.get("pending") or []
            ],
            answers=dict(d.get("answers") or {}),
            request_inputs=list(d.get("request_inputs") or []),
            teaching_summaries=dict(d.get("teaching_summaries") or {}),
            usage=dict(d.get("usage") or {}),
            turn=int(d.get("turn", 0)),
            finished=bool(d.get("finished", False)),
            created_at=d.get("created_at") or datetime.now(UTC).isoformat(),
            updated_at=d.get("updated_at") or datetime.now(UTC).isoformat(),
        )
        if "answer_hashes" not in d:
            session.answer_hashes = session._legacy_answer_hashes()
        return session

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
