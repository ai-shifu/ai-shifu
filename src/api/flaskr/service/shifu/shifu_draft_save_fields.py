"""Field containers for ``save_shifu_draft_info``.

The draft save resolves caller fields against the current draft before it
writes a new draft row; these helpers hold that resolved state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal


@dataclass
class _SaveTtsSettings:
    """Merged TTS fields for a draft save plus which ones the caller sent."""

    provider: str | None
    model: str | None
    voice_id: str | None
    speed: float | None
    pitch: int | None
    emotion: str | None
    default_listen_mode_enabled: bool | None
    provider_provided: bool
    model_provided: bool
    voice_provided: bool
    speed_provided: bool
    pitch_provided: bool
    emotion_provided: bool


@dataclass
class _SaveAskSettings:
    """Resolved ask fields for a draft save."""

    enabled_status: int
    model: str
    model_provided: bool
    temperature: float
    system_prompt: str
    serialized_provider_config: str


@dataclass
class _ShifuDraftUpdate:
    """All resolved inputs of one ``save_shifu_draft_info`` call."""

    name: str | None
    description: str | None
    avatar: str | None
    keywords: list[str] | None
    model: str | None
    temperature: float | None
    price: Decimal
    system_prompt: str | None
    tts_enabled: bool | None
    use_learner_language: bool | None
    tts: _SaveTtsSettings
    ask: _SaveAskSettings
