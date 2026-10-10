"""Read exact learner wording from the already authorized follow-up window."""

from __future__ import annotations

import json
from dataclasses import dataclass

QUOTATION_RESULT_BYTES = 8192
QUOTATION_PAGE_SIZE = 20


def _encode(value: dict) -> str:
    """Use the wire representation when checking the complete UTF-8 result."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class LearnerQuotationSource:
    """Immutable original learner messages, excluding the current question."""

    messages: tuple[str, ...]

    @classmethod
    def from_history(cls, history: list[dict[str, str]]) -> LearnerQuotationSource:
        """Select only original user roles before any host prompt projection."""
        prior = history[:-1] if history and history[-1]["role"] == "user" else history
        return cls(tuple(m["content"] for m in prior if m["role"] == "user"))

    def read(self, offset: int = 0) -> str:
        """Page complete messages; oversized entries are unavailable, never truncated."""
        if offset < 0 or offset > len(self.messages):
            return _encode({"status": "invalid_offset"})
        entries: list[dict] = []
        cursor = offset

        def result(items: list[dict], end: int) -> str:
            """Include provenance and pagination inside the byte budget."""
            return _encode(
                {
                    "status": "learner_messages",
                    "coverage": "supplied_history_only",
                    "messages": items,
                    "next_offset": end if end < len(self.messages) else None,
                }
            )

        while cursor < len(self.messages) and len(entries) < QUOTATION_PAGE_SIZE:
            entry = {
                "source_index": cursor,
                "role": "learner",
                "status": "available",
                "content": self.messages[cursor],
            }
            if (
                len(result([*entries, entry], cursor + 1).encode("utf-8"))
                > QUOTATION_RESULT_BYTES
            ):
                if entries:
                    break
                entry = {
                    "source_index": cursor,
                    "role": "learner",
                    "status": "too_large",
                }
            entries.append(entry)
            cursor += 1
        return result(entries, cursor)

    def page_count(self) -> int:
        """Reserve enough tool calls to read this window once, including empty history."""
        offset, pages = 0, 0
        while offset is not None:
            offset = json.loads(self.read(offset))["next_offset"]
            pages += 1
        return pages
