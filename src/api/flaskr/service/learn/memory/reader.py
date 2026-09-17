"""Read a learner's stored answers, with course scope winning over the global scope."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from flaskr.service.profile.models import VariableValue

if TYPE_CHECKING:
    from datetime import datetime

    from flask import Flask


GLOBAL_SCOPE = ""
"""`shifu_bid` of a value that follows the learner rather than belonging to one course."""

# These three are written to the variable table for compatibility but read back from the user
# record, so the rows here can be stale. `get_user_profiles` overrides them for the same reason.
# Reading them from this package would disagree with what a lesson actually sees.
ENTITY_OWNED_KEYS = frozenset(
    {"sys_user_nickname", "sys_user_language", "sys_user_background"}
)

DEFAULT_ROW_LIMIT = 2000
"""A cap on rows read per learner. The table is append-only and has no composite index, so a
long-running learner can accumulate thousands; newest first means a cap loses only old history."""

Scope = Literal["course", "global"]


@dataclass(frozen=True)
class MemoryEntry:
    """One thing the learner told us, and where they told us."""

    key: str
    value: str
    scope: Scope
    shifu_bid: str
    updated_at: datetime | None = None

    @property
    def is_global(self) -> bool:
        """Whether this value follows the learner rather than belonging to one course."""
        return self.scope == "global"


@dataclass(frozen=True)
class LearnerMemory:
    """What is known about a learner when a given course asks.

    `entries` is what that course would see: its own values, falling back to the global scope,
    newest first. `elsewhere` is everything the same learner answered in *other* courses, grouped
    by key and never merged into `entries`.

    The separation is deliberate. Across production data, 65% of the learners who answered the
    same variable name in two courses gave **different** answers, because each course writes its
    own option set: `learner_role` agrees in 3 cases out of 53, and course-local assessments such
    as `base_level` agree in none. Folding those together by name would teach a learner using
    another course's answer. Anything cross-course has to be an explicit decision, so this type
    hands it over rather than deciding.
    """

    user_bid: str
    shifu_bid: str | None
    entries: dict[str, MemoryEntry] = field(default_factory=dict)
    elsewhere: dict[str, list[MemoryEntry]] = field(default_factory=dict)
    truncated: bool = False

    def as_variables(self) -> dict[str, str]:
        """Flatten to the `{key: value}` shape a prompt template expects."""
        return {key: entry.value for key, entry in self.entries.items()}

    def get(self, key: str, default: str | None = None) -> str | None:
        """Look up one live value."""
        entry = self.entries.get(key)
        return entry.value if entry else default

    @property
    def global_keys(self) -> list[str]:
        """Which live values came from the global scope rather than this course."""
        return sorted(k for k, e in self.entries.items() if e.is_global)


def _to_entry(row: VariableValue) -> MemoryEntry:
    shifu_bid = row.shifu_bid or GLOBAL_SCOPE
    return MemoryEntry(
        key=row.key,
        value=row.value,
        scope="global" if shifu_bid == GLOBAL_SCOPE else "course",
        shifu_bid=shifu_bid,
        updated_at=row.updated_at,
    )


def load_learner_memory(
    app: Flask,
    user_bid: str,
    *,
    shifu_bid: str | None = None,
    include_entity_owned: bool = False,
    limit: int = DEFAULT_ROW_LIMIT,
) -> LearnerMemory:
    """Everything this learner has answered, as the given course would see it.

    `shifu_bid` selects the course scope; passing None reads the global scope only and reports
    every course's answers under `elsewhere`. Precedence inside `entries` follows what lessons
    already do today: the course's own value first, then the global one, newest by row id.

    The three keys owned by the user record are skipped unless `include_entity_owned` is set,
    because their rows here are write-only compatibility data and can disagree with the lesson.
    """
    _ = app  # the session comes from the app context; kept for call-site symmetry
    rows: list[VariableValue] = (
        VariableValue.query.filter(
            VariableValue.user_bid == user_bid,
            VariableValue.deleted == 0,
        )
        .order_by(VariableValue.id.desc())
        .limit(limit + 1)
        .all()
    )
    truncated = len(rows) > limit
    if truncated:
        rows = rows[:limit]

    entries: dict[str, MemoryEntry] = {}
    elsewhere: dict[str, list[MemoryEntry]] = {}
    seen_elsewhere: set[tuple[str, str]] = set()

    # Rows arrive newest first, so the first one seen for a (scope, key) is the live one.
    for row in rows:
        if not row.key or (row.key in ENTITY_OWNED_KEYS and not include_entity_owned):
            continue
        entry = _to_entry(row)
        in_scope = entry.shifu_bid == (shifu_bid or GLOBAL_SCOPE) or entry.is_global
        if in_scope:
            current = entries.get(entry.key)
            # A course value outranks a global one even though it may be older.
            if current is None or (current.is_global and not entry.is_global):
                entries[entry.key] = entry
            continue
        marker = (entry.shifu_bid, entry.key)
        if marker not in seen_elsewhere:
            seen_elsewhere.add(marker)
            elsewhere.setdefault(entry.key, []).append(entry)

    return LearnerMemory(
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        entries=entries,
        elsewhere=elsewhere,
        truncated=truncated,
    )
