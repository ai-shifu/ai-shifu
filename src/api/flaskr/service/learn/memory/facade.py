"""Load and stage learner memory through the supported category adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.service.learn.memory.dtos import MemorySnapshot, MemoryUpdate
from flaskr.service.profile.api import get_user_profiles, save_user_profiles
from flaskr.service.profile.dtos import ProfileToSave

if TYPE_CHECKING:
    from flask import Flask


def load_memory(app: Flask, user_bid: str, shifu_bid: str) -> MemorySnapshot:
    """Read supported memory categories for an authorized user/course context.

    Variables currently use runtime profile resolution, including settings edits
    and canonical fields. The broad reader's ``elsewhere`` is not merged.
    """
    return MemorySnapshot(variables=get_user_profiles(app, user_bid, shifu_bid))


def stage_memory(
    app: Flask, user_bid: str, shifu_bid: str, update: MemoryUpdate
) -> bool:
    """Stage a memory patch in the caller's existing app/DB context.

    Variables use the existing profile writer. Copy its mapped values back to
    the variable payloads for update events; profile DTOs stay inside this adapter.
    Empty patches are no-ops. The boolean is the writer result, not a durability
    guarantee: the writer flushes and the caller owns the commit.
    """
    if not update.variables:
        return True
    profiles = [
        ProfileToSave(item.key, item.value, item.definition_bid)
        for item in update.variables
    ]
    saved = save_user_profiles(app, user_bid, shifu_bid, profiles)
    for item, profile in zip(update.variables, profiles, strict=True):
        item.value = profile.value
    return saved
