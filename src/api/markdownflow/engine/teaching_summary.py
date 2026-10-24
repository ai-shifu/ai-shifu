"""Bounded, session-local semantic decoration of exact teaching excerpts."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

SUMMARY_SOURCE_BYTES = 32_768
SUMMARY_TEXT_BYTES = 1024
SUMMARY_CACHE_ENTRIES = 64


def encoded_size(text: str) -> int:
    """Count JSON-escaped UTF-8 bytes, including quotes."""
    return len(json.dumps(text, ensure_ascii=False).encode("utf-8"))


@dataclass(frozen=True)
class TeachingSummarizer:
    """A host's policy identity and isolated, fallible summary callback."""

    policy: str
    summarize: Callable[[str], Awaitable[str | None]]


async def summarize_teaching_history(
    messages: list[ModelMessage],
    sources: dict[str, str],
    cache: dict[str, str],
    summarizer: TeachingSummarizer,
) -> list[ModelMessage]:
    """Decorate current exact excerpts with bounded cached semantic overviews.

    At most one uncached complete source is sent to the callback per turn. Empty
    entries remember failures so an unavailable summary cannot repeatedly bill a
    learner. Original source text and the recent two turns stay untouched.
    """
    references = list(sources)[-SUMMARY_CACHE_ENTRIES:]
    keys = {reference: f"{summarizer.policy}:{reference}" for reference in references}
    retained = {
        key: value
        for key in keys.values()
        if isinstance((value := cache.get(key)), str)
        and encoded_size(value) <= SUMMARY_TEXT_BYTES
    }
    cache.clear()
    cache.update(retained)
    for reference in reversed(references):
        key = keys[reference]
        if key in cache:
            continue
        source = sources[reference]
        cache[key] = ""
        if encoded_size(source) > SUMMARY_SOURCE_BYTES:
            continue
        try:
            summary = await summarizer.summarize(source)
        except Exception:
            # A derivative is optional; original evidence remains available.
            summary = None
        if (
            isinstance(summary, str)
            and summary.strip()
            and encoded_size(summary) <= SUMMARY_TEXT_BYTES
        ):
            cache[key] = summary
        break

    projected = list(messages)
    for index, message in enumerate(messages):
        if not isinstance(message, ModelResponse):
            continue
        parts = list(message.parts)
        for part_index, part in enumerate(message.parts):
            if not isinstance(part, TextPart):
                continue
            try:
                marker = json.loads(part.content)
            except ValueError:
                continue
            if (
                not isinstance(marker, dict)
                or marker.get("status") != "teaching_excerpt"
            ):
                continue
            reference = marker.get("reference")
            if (
                not isinstance(reference, str)
                or reference not in keys
                or not reference.startswith(f"teaching-{index}-{part_index}-")
            ):
                continue
            summary = cache.get(keys[reference])
            if not summary:
                continue
            marker.update(
                status="teaching_summary",
                summary=summary,
                notice="Lossy historical overview. Use read_teaching for exact evidence.",
            )
            text = json.dumps(marker, ensure_ascii=False, separators=(",", ":"))
            if encoded_size(text) < encoded_size(sources[reference]):
                parts[part_index] = replace(part, content=text)
        if parts != message.parts:
            projected[index] = replace(message, parts=parts)
    return projected
