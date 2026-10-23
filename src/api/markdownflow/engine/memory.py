"""Learner memory.

The engine keeps session memory on the session; user-scoped memory goes through a host-provided
store so it can outlive the session.
"""

from __future__ import annotations

from typing import Any, Protocol


class MemoryStore(Protocol):
    """Where user-scoped memory is kept between sessions."""

    async def load(self, user_id: str) -> dict[str, Any]:
        """Return everything remembered about this user."""

    async def save(self, user_id: str, memory: dict[str, Any]) -> None:
        """Replace everything remembered about this user."""


class InMemoryMemoryStore:
    """A memory store that lasts as long as the process. For tests and demos."""

    def __init__(self) -> None:
        """Start empty."""
        self._data: dict[str, dict[str, Any]] = {}

    async def load(self, user_id: str) -> dict[str, Any]:
        """Return everything remembered about this user."""
        return dict(self._data.get(user_id, {}))

    async def save(self, user_id: str, memory: dict[str, Any]) -> None:
        """Replace everything remembered about this user."""
        self._data[user_id] = dict(memory)
