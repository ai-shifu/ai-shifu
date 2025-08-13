"""Redis based cache utilities for shifu structs and outlines.

This module provides helper functions to cache shifu structs and outline
trees in Redis with concurrency control. It exposes utilities to build
cache keys, fetch or populate cache values under a Redis lock and remove
cached entries when data is updated.

Author: yfge (added by open-source contributor)
"""

from typing import Callable

from flaskr.dao import redis_client
from flaskr.common.config import get_config


def _prefix() -> str:
    """Return configured Redis key prefix."""
    return get_config("REDIS_KEY_PREFIX", "ai-shifu:")


STRUCT_PREFIX = _prefix() + "shifu_struct:"
OUTLINE_PREFIX = _prefix() + "shifu_outline:"


def struct_cache_key(shifu_bid: str, is_preview: bool) -> str:
    """Build cache key for shifu struct."""
    mode = "preview" if is_preview else "pub"
    return f"{STRUCT_PREFIX}{mode}:{shifu_bid}"


def outline_cache_key(shifu_bid: str, is_preview: bool) -> str:
    """Build cache key for shifu outline tree."""
    mode = "preview" if is_preview else "pub"
    return f"{OUTLINE_PREFIX}{mode}:{shifu_bid}"


def get_or_set(key: str, loader: Callable[[], str], expire: int) -> str:
    """Get a cache entry or populate it using loader under a Redis lock."""
    cached = redis_client.get(key)
    if cached is not None:
        return cached.decode("utf-8") if isinstance(cached, bytes) else cached

    lock = redis_client.lock(key + ":lock", timeout=5, blocking_timeout=5)
    acquired = lock.acquire(blocking=False)
    try:
        if acquired:
            cached = redis_client.get(key)
            if cached is not None:
                return cached.decode("utf-8") if isinstance(cached, bytes) else cached
            value = loader()
            if value is not None:
                redis_client.set(key, value, ex=expire)
            return value
        # Lock not acquired, fall back to direct load
        return loader()
    finally:
        if acquired:
            try:
                lock.release()
            except Exception:
                pass


def delete_shifu_cache(shifu_bid: str) -> None:
    """Remove cached struct and outline for given shifu."""
    redis_client.delete(struct_cache_key(shifu_bid, False))
    redis_client.delete(struct_cache_key(shifu_bid, True))
    redis_client.delete(outline_cache_key(shifu_bid, False))
    redis_client.delete(outline_cache_key(shifu_bid, True))
