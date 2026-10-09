"""Select the MarkdownFlow runtime for this deployment.

Simulation and production share a database, so runtime selection must read only
the environment registry, never the service helper that falls back to
``sys_configs``. Enabling this flag sends every course to 2.0; unset, false or
malformed values retain 1.0. The retired course allowlist has no effect.
"""

from __future__ import annotations

from flaskr.common.config import get_config

V2_ENABLED_CONFIG_KEY = "FLOW_ENGINE_V2_ENABLED"


def uses_agent_engine(shifu_bid: object) -> bool:
    """Report whether an identified course uses 2.0 in this deployment."""
    if not str(shifu_bid or "").strip():
        return False
    raw = get_config(V2_ENABLED_CONFIG_KEY, default=False)
    # The registry returns raw environment strings before Config initializes
    # and parsed booleans afterwards. In particular, bool("false") is unsafe.
    return raw is True or (
        isinstance(raw, str) and raw.strip().lower() in {"true", "1", "yes", "on"}
    )
