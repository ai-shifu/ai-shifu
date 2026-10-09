"""Generate isolated teaching summaries through the shared billed model gateway."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_ai import Agent, UsageLimits

from .engine.teaching_summary import (
    SUMMARY_TEXT_BYTES,
    TeachingSummarizer,
    encoded_size,
)

if TYPE_CHECKING:
    from pydantic_ai.models import Model


def make_teaching_summarizer(model: Model) -> TeachingSummarizer:
    """Bind a prompt/model policy; the engine owns source limits and cache scope."""
    instructions = (
        Path(__file__).parent / "engine/prompts/teaching_summary.md"
    ).read_text()
    policy = hashlib.sha256(
        f"teaching-summary-v1:{model.model_name}:{instructions}".encode()
    ).hexdigest()
    agent = Agent(
        model,
        instructions=instructions,
        retries=0,
        model_settings={"temperature": 0, "max_tokens": 256},
    )

    async def summarize(source: str) -> str | None:
        """Use one logical request; invalid/failed summaries leave exact excerpts."""
        try:
            result = await agent.run(
                json.dumps({"historical_teaching": source}, ensure_ascii=False),
                usage_limits=UsageLimits(request_limit=1, tool_calls_limit=0),
            )
        except Exception:
            return None
        text = result.output.strip()
        if not text or encoded_size(text) > SUMMARY_TEXT_BYTES:
            return None
        return text

    return TeachingSummarizer(policy=policy, summarize=summarize)
