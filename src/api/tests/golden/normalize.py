"""Normalizer for golden regression fixtures.

Golden fixtures capture the byte-level SSE output of ``/run`` and the JSON of
key non-SSE endpoints. Some values are inherently volatile across runs (fresh
UUIDs, autoincrement ids, timestamps). This module rewrites only those values
into stable placeholders while keeping everything that is part of the frontend
contract verbatim.

Normalization rules (everything else is kept byte-identical):

- Generated business identifiers: any 32-char lowercase-hex string (the shape
  produced by ``flaskr.util.generate_id`` / ``uuid.uuid4().hex``) and any
  dashed UUID are replaced with ``<BID_1>``, ``<BID_2>``, ... using a
  first-seen mapping. The mapping is shared for a whole transcript/payload, so
  identity relations are preserved: two events that reference the same
  ``generated_block_bid`` map to the same placeholder. The substitution also
  applies to hex ids embedded inside longer strings.
- ISO-8601 timestamps (e.g. ``2026-07-03T10:00:00Z``, with or without
  fractional seconds / offset, ``T`` or space separated) -> ``<TS>``.
- Volatile integer record ids: integer values under the field names listed in
  ``VOLATILE_INT_FIELDS`` (currently only ``id``, the autoincrement primary
  key) -> ``<ID>``.
- Heartbeat SSE events (``type == "heartbeat"``) are dropped defensively.
  Golden tests disable heartbeats via ``SSE_HEARTBEAT_INTERVAL = 0``, but the
  transcript must stay stable even if a heartbeat slips through.

Explicitly NOT normalized (these are the contract):

- Event order, ``type`` / ``event_type`` values, ``run_event_seq``,
  ``sequence_number``, ``element_index``, ``is_terminal`` flags.
- Seeded human-readable bids (e.g. ``golden-lesson-0001``) -- they are
  deterministic test inputs and do not match the hex-id shape.
- All content strings (modulo embedded hex ids / timestamps).
"""

from __future__ import annotations

import json
import re
from typing import Any

HEX_ID_RE = re.compile(r"\b[0-9a-f]{32}\b")
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
)
ISO_TS_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)

VOLATILE_INT_FIELDS = frozenset({"id"})

SSE_DATA_PREFIX = "data: "


class IdNormalizer:
    """First-seen mapping of volatile ids to stable placeholders."""

    def __init__(self) -> None:
        self._mapping: dict[str, str] = {}

    def _replace_match(self, match: re.Match) -> str:
        raw = match.group(0)
        if raw not in self._mapping:
            self._mapping[raw] = f"<BID_{len(self._mapping) + 1}>"
        return self._mapping[raw]

    def normalize_string(self, value: str) -> str:
        value = UUID_RE.sub(self._replace_match, value)
        value = HEX_ID_RE.sub(self._replace_match, value)
        value = ISO_TS_RE.sub("<TS>", value)
        return value

    def normalize_value(self, value: Any, field_name: str | None = None) -> Any:
        if isinstance(value, str):
            return self.normalize_string(value)
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and field_name in VOLATILE_INT_FIELDS:
            return "<ID>"
        if isinstance(value, dict):
            return {
                key: self.normalize_value(item, field_name=key)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.normalize_value(item, field_name=field_name) for item in value]
        return value


def parse_sse_events(raw_transcript: str) -> list[dict]:
    """Parse ``data: {json}`` SSE lines into a list of event dicts."""
    events: list[dict] = []
    for chunk in raw_transcript.split("\n\n"):
        chunk = chunk.strip()
        if not chunk.startswith(SSE_DATA_PREFIX):
            continue
        payload = chunk[len(SSE_DATA_PREFIX) :].strip()
        if not payload:
            continue
        events.append(json.loads(payload))
    return events


def normalize_sse_transcript(
    raw_transcript: str, normalizer: IdNormalizer | None = None
) -> str:
    """Normalize a raw SSE transcript into one stable JSON line per event."""
    normalizer = normalizer or IdNormalizer()
    lines: list[str] = []
    for event in parse_sse_events(raw_transcript):
        if event.get("type") == "heartbeat":
            continue
        normalized = normalizer.normalize_value(event)
        lines.append(json.dumps(normalized, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def normalize_json_payload(payload: Any, normalizer: IdNormalizer | None = None) -> str:
    """Normalize a JSON response payload into a stable pretty-printed string."""
    normalizer = normalizer or IdNormalizer()
    normalized = normalizer.normalize_value(payload)
    return json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
