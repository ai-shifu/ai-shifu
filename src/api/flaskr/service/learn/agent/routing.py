"""Decide which MarkdownFlow runtime teaches a course.

The allowlist lives in the environment, not in the database, and that is deliberate. The
simulation environment shares one database with production, so a per-course column cannot express
"2.0 here, 1.0 there": both read the same row, and a course switched on in simulation would switch
for paying learners the moment 2.0 ships. An environment variable belongs to the deployment, so the
same code and the same data behave differently in each one.

Empty means every course stays on 1.0. That is also what a malformed value gives: routing a learner
into a runtime nobody chose is worse than ignoring a typo, so every failure here resolves to 1.0.

The value is read through ``flaskr.common.config``, not through the service-level helper the rest of
this package uses. The service helper falls back to the ``sys_configs`` table when no environment
variable is set, and that table lives in the very database the two deployments share -- a row there
would reach production exactly the way the column this module exists to avoid would. Reading the
environment registry keeps the decision where the deployment can own it.

This whole module is migration scaffolding. Once every course runs 2.0 there is nothing left to
select, and it goes away with the allowlist.
"""

from __future__ import annotations

from flaskr.common.config import get_config

# Comma separated course business identifiers taught by the 2.0 engine.
V2_SHIFU_BIDS_CONFIG_KEY = "FLOW_ENGINE_V2_SHIFU_BIDS"


def _parse_shifu_bids(raw: object) -> frozenset[str]:
    """Read an allowlist out of whatever the config layer hands back.

    The value arrives as a list once the config singleton has parsed it, and as the raw string
    before that, so both are accepted. Nothing else is: a mapping is iterable too, and iterating it
    would quietly turn its keys into an allowlist. Blank entries are dropped rather than kept as an
    empty identifier that would match a course with no bid.
    """
    if isinstance(raw, str):
        candidates: list[object] = list(raw.split(","))
    elif isinstance(raw, list):
        candidates = list(raw)
    else:
        return frozenset()
    return frozenset(
        stripped
        for stripped in (str(candidate or "").strip() for candidate in candidates)
        if stripped
    )


def get_v2_shifu_bids() -> frozenset[str]:
    """Return the courses the 2.0 engine teaches in this deployment."""
    return _parse_shifu_bids(get_config(V2_SHIFU_BIDS_CONFIG_KEY, default=""))


def uses_agent_engine(shifu_bid: object) -> bool:
    """Report whether this course is taught by the 2.0 engine here."""
    normalized = str(shifu_bid or "").strip()
    if not normalized:
        return False
    return normalized in get_v2_shifu_bids()
