"""Provider dispatch for cloned TTS voices (read path).

Cloned-voice asset management grew up MiniMax-only. This module carries the
per-provider facts (custom id format, synthesis model requirement, validation
strictness) so validation / preview / runtime code can stay free of provider
literals. Voice id shapes overlap across providers (an ``S_xxxxxxxxxx`` id also
matches MiniMax's rule), so callers must always dispatch on the provider
name, never on the id format.

Adding a provider = one spec entry here, plus a verifier on the operator
write path (``admin_operations/voice_clones.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from flaskr.service.tts.minimax_voice_clone import is_valid_minimax_custom_voice_id
from flaskr.service.tts.models import (
    TTS_CLONE_PROVIDER_MINIMAX,
    TTS_CLONE_PROVIDER_VOLCENGINE,
    TTS_MINIMAX_CLONE_STATUS_READY,
    TTSMiniMaxClonedVoice,
)
from flaskr.service.tts.volcengine_voice_clone import (
    is_valid_volcengine_custom_voice_id,
)


@dataclass(frozen=True)
class ClonedVoiceProviderSpec:
    provider: str
    is_valid_custom_voice_id: Callable[[str], bool]
    # Whether strict validation demands a ready DB row. MiniMax keeps its
    # historical format-only bypass; volcengine ids must be registered.
    # Note: provider-specific synthesis resources (volcengine cloned voices
    # run under seed-icl-2.0) are inferred inside the provider from the voice
    # id, so no model constraint is enforced here.
    validation_requires_ready_row: bool


_CLONE_PROVIDER_SPECS: dict[str, ClonedVoiceProviderSpec] = {
    TTS_CLONE_PROVIDER_MINIMAX: ClonedVoiceProviderSpec(
        provider=TTS_CLONE_PROVIDER_MINIMAX,
        is_valid_custom_voice_id=is_valid_minimax_custom_voice_id,
        validation_requires_ready_row=False,
    ),
    TTS_CLONE_PROVIDER_VOLCENGINE: ClonedVoiceProviderSpec(
        provider=TTS_CLONE_PROVIDER_VOLCENGINE,
        is_valid_custom_voice_id=is_valid_volcengine_custom_voice_id,
        validation_requires_ready_row=True,
    ),
}


def get_clone_provider_spec(provider: str) -> Optional[ClonedVoiceProviderSpec]:
    return _CLONE_PROVIDER_SPECS.get((provider or "").strip().lower())


def supports_cloned_voices(provider: str) -> bool:
    return get_clone_provider_spec(provider) is not None


def find_ready_cloned_voice(
    *, provider: str, voice_id: str, owner_user_bid: Optional[str] = None
) -> Optional[TTSMiniMaxClonedVoice]:
    """Latest ready, non-deleted clone row for (provider, voice_id).

    ``owner_user_bid=None`` skips owner scoping (strict validation, runtime);
    passing a string filters by that exact owner, so an empty string matches
    nothing (preview guard semantics).
    """
    normalized_voice_id = (voice_id or "").strip()
    if not normalized_voice_id:
        return None
    query = TTSMiniMaxClonedVoice.query.filter(
        TTSMiniMaxClonedVoice.provider == (provider or "").strip().lower(),
        TTSMiniMaxClonedVoice.voice_id == normalized_voice_id,
        TTSMiniMaxClonedVoice.status == TTS_MINIMAX_CLONE_STATUS_READY,
        TTSMiniMaxClonedVoice.deleted == 0,
    )
    if owner_user_bid is not None:
        query = query.filter(
            TTSMiniMaxClonedVoice.owner_user_bid == owner_user_bid.strip()
        )
    return query.order_by(TTSMiniMaxClonedVoice.id.desc()).first()


def find_tracked_cloned_voice(
    *, provider: str, voice_id: str, shifu_bid: str
) -> Optional[TTSMiniMaxClonedVoice]:
    """Latest non-deleted row this shifu tracks, regardless of status."""
    normalized_voice_id = (voice_id or "").strip()
    if not normalized_voice_id:
        return None
    return (
        TTSMiniMaxClonedVoice.query.filter(
            TTSMiniMaxClonedVoice.provider == (provider or "").strip().lower(),
            TTSMiniMaxClonedVoice.voice_id == normalized_voice_id,
            TTSMiniMaxClonedVoice.shifu_bid == (shifu_bid or "").strip(),
            TTSMiniMaxClonedVoice.deleted == 0,
        )
        .order_by(TTSMiniMaxClonedVoice.id.desc())
        .first()
    )
