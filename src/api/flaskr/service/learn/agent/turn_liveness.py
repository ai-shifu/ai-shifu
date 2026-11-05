"""Tell a turn whose run is still going from one whose run died.

A turn's block is written before the turn streams and filled in when it ends. When the learner's
request goes away the lesson lock is released at once, but the run keeps going on its producer
thread and may still fill the block in -- a structured answer saves its text late. A block left
empty is therefore either a run still in progress or a run that died before it saved, and only
the second may be retired.

The run says which while it lasts: it holds a short-lived Redis key per block, refreshed from its
own thread and deleted when the run ends. A process that dies stops refreshing, so its key
expires within `TURN_LIVENESS_TTL_SECONDS`. Only a shared Redis can answer for runs on other
workers; without one the answer is unknown and callers keep their age-based rule.
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

# The key outlives one missed refresh, so a slow Redis round trip does not make a live run look
# dead; a dead process is noticed within this long.
TURN_LIVENESS_TTL_SECONDS = 60
TURN_LIVENESS_REFRESH_SECONDS = 20


def _key(app: Flask | None, generated_block_bid: str) -> str:
    config = getattr(app, "config", None) or {}
    prefix = config.get("REDIS_KEY_PREFIX") or "ai-shifu"
    return f"{prefix}:turn_live:{generated_block_bid}"


@contextlib.contextmanager
def hold_turn_liveness(app: Flask | None, generated_block_bid: str) -> Iterator[None]:
    """Mark the block as owned by a running turn for as long as the block runs.

    Entered before the block becomes visible to other requests, so no reader sees the block
    without its mark. A failed write is logged and the turn goes on: the lesson matters more
    than the mark, and a reader that finds no mark still waits a minimum age.
    """
    key = _key(app, generated_block_bid)
    stop = threading.Event()
    # Serializes refreshes with the final delete, so a refresh already under way cannot put
    # the key back after the turn has ended.
    guard = threading.Lock()
    failed = False

    def mark() -> None:
        nonlocal failed
        with guard:
            if stop.is_set():
                return
            try:
                redis_cache.setex(key, TURN_LIVENESS_TTL_SECONDS, "1")
            except Exception as exc:
                # Liveness must not break the turn. Logged once: without Redis every
                # refresh fails the same way.
                if failed:
                    return
                failed = True
                getattr(app, "logger", _logger).warning(
                    "turn liveness mark failed: generated_block_bid=%s error=%s",
                    generated_block_bid,
                    type(exc).__name__,
                )

    def refresh() -> None:
        while not stop.wait(TURN_LIVENESS_REFRESH_SECONDS):
            mark()

    mark()
    refresher = threading.Thread(
        target=refresh, name="turn_liveness_refresh", daemon=True
    )
    refresher.start()
    try:
        yield
    finally:
        with guard:
            stop.set()
            with contextlib.suppress(Exception):
                redis_cache.delete(key)


def turn_is_live(app: Flask | None, generated_block_bid: str) -> bool | None:
    """Report whether a run holds the block: True, False, or None when Redis cannot say."""
    try:
        return redis_cache.get(_key(app, generated_block_bid)) is not None
    except Exception:
        # Unknown: callers fall back to the block's age.
        return None
