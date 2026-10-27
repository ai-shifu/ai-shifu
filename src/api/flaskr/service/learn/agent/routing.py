"""Select the MarkdownFlow runtime for a course.

Every identified course is taught by 2.0. ``FLOW_ENGINE_V2_ENABLED`` is no longer
read; it stays registered until deployments stop setting it and the 1.0 runtime
is deleted.
"""

from __future__ import annotations


def uses_agent_engine(shifu_bid: object) -> bool:
    """Report whether a course uses 2.0: every identified course does."""
    return bool(str(shifu_bid or "").strip())
