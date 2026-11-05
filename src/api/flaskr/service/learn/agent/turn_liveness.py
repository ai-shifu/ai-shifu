"""Tell a turn whose run is still going from one whose run has ended.

A turn's block is written before the turn streams and filled in when it ends. When the learner's
request goes away the lesson lock is released at once, but the run keeps going on its producer
thread and may still fill the block in -- a structured answer saves its text late. A block left
empty is therefore either a run still in progress or a run that ended without saving, and only
the second may be retired.

The run says which in a Redis key per block: "live" while it runs, refreshed from its own
thread, and "ended" once it is over. Only an "ended" key proves the run is gone. A missing key
proves nothing -- the write may have failed, the process may have died, or the worker may
predate the key -- so callers keep their age-based rule for it, as they do when Redis cannot be
read at all. Only a shared Redis can answer for runs on other workers.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import TYPE_CHECKING

from flaskr.common.cache_provider import redis_cache

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask

_logger = logging.getLogger(__name__)

_LIVE = "live"
_ENDED = "ended"

# The live key outlives one missed refresh, so a slow Redis round trip does not make a running
# turn look gone; a process that dies stops refreshing and its key expires within this long.
TURN_LIVENESS_TTL_SECONDS = 60
TURN_LIVENESS_REFRESH_SECONDS = 20
# How long the ended state is kept. Past `rewind.ABANDONED_TURN_GRACE` (10 minutes) the age rule
# alone treats an empty block as abandoned, so the state is not needed after that.
TURN_ENDED_TTL_SECONDS = 10 * 60


def _key(app: Flask | None, generated_block_bid: str) -> str:
    config = getattr(app, "config", None) or {}
    prefix = config.get("REDIS_KEY_PREFIX") or "ai-shifu"
    return f"{prefix}:turn_live:{generated_block_bid}"


@contextlib.contextmanager
def hold_turn_liveness(app: Flask | None, generated_block_bid: str) -> Iterator[None]:
    """Mark the block live while the turn runs, and ended once it is over.

    Entered before the block becomes visible to other requests. A failed write is logged and
    the turn goes on: the lesson matters more than the mark, and a reader that finds no mark
    falls back to the block's age.
    """
    key = _key(app, generated_block_bid)
    stop = threading.Event()
    # Serializes refreshes with the final write, so a refresh already under way cannot turn an
    # ended block back into a live one.
    guard = threading.Lock()
    failed = False

    def write(state: str, ttl: int) -> None:
        nonlocal failed
        try:
            redis_cache.setex(key, ttl, state)
        except Exception as exc:
            # Liveness must not break the turn. Logged once: without Redis every write fails
            # the same way.
            if failed:
                return
            failed = True
            getattr(app, "logger", _logger).warning(
                "turn liveness mark failed: generated_block_bid=%s error=%s",
                generated_block_bid,
                type(exc).__name__,
            )

    def mark_live() -> None:
        with guard:
            if not stop.is_set():
                write(_LIVE, TURN_LIVENESS_TTL_SECONDS)

    def refresh() -> None:
        while not stop.wait(TURN_LIVENESS_REFRESH_SECONDS):
            mark_live()

    mark_live()
    refresher = threading.Thread(
        target=refresh, name="turn_liveness_refresh", daemon=True
    )
    refresher.start()
    try:
        yield
    finally:
        with guard:
            stop.set()
            write(_ENDED, TURN_ENDED_TTL_SECONDS)


def turn_is_live(app: Flask | None, generated_block_bid: str) -> bool | None:
    """Report whether a run holds the block.

    True while it runs, False once it has said it ended, and None when nothing can be told: no
    key (never written, lost, or expired) or Redis unreadable.
    """
    try:
        raw = redis_cache.get(_key(app, generated_block_bid))
    except Exception:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    if raw == _LIVE:
        return True
    if raw == _ENDED:
        return False
    return None
