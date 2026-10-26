"""Shared stand-ins for the agent tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


class SynchronousFinalizer:
    """The finalize drainer, without the thread.

    The real one finishes a retired processor on a background thread inside an app context, which
    the stubs here do not have; a thread that dies before reporting leaves `drain(wait=True)`
    waiting forever. Finishing inline keeps the tests honest about ordering and hang-free.
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Accept whatever the real drainer is built with, and ignore it."""
        self._owed: list = []
        self.closed = False

    def submit(self, processor: object) -> None:
        self._owed.extend(processor.finalize(commit=True))

    def drain(self, *, wait: bool = False) -> Iterator:  # noqa: ARG002
        owed, self._owed = self._owed, []
        yield from owed

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _finalize_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "flaskr.service.learn.agent.listen.StreamTTSFinalizeDrainer",
        SynchronousFinalizer,
    )
