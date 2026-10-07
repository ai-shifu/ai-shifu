"""Independently verify explicit learner requests through the existing model gateway."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel
from pydantic_ai import Agent, UsageLimits

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pydantic_ai.models import Model


class MemoryDecision(BaseModel):
    """Whether the actual learner input explicitly authorizes the proposed memory value."""

    allowed: bool


def make_request_check(model: Model) -> Callable[[str, str, str], Awaitable[bool]]:
    """Cache at most three independent checks per host request; errors refuse admission."""
    judge = Agent(
        model,
        output_type=MemoryDecision,
        instructions=(
            Path(__file__).parent / "engine/prompts/memory_admission.md"
        ).read_text(),
        retries=0,
        model_settings={"temperature": 0, "max_tokens": 512},
    )
    checks: dict[tuple[str, str, str], asyncio.Task[bool]] = {}

    async def decide(request: str, key: str, value: str) -> bool:
        """Make one structured semantic decision without exposing judge output to learners."""
        try:
            result = await judge.run(
                json.dumps(
                    {"learner_input": request, "key": key, "value": value},
                    ensure_ascii=False,
                ),
                usage_limits=UsageLimits(request_limit=1, tool_calls_limit=1),
            )
        except Exception:
            # Provider/validation failures cannot become permission or interrupt teaching.
            return False
        else:
            return result.output.allowed

    async def check(request: str, key: str, value: str) -> bool:
        """Deduplicate concurrent repeated calls and enforce the bounded extra call count."""
        identity = (request, key, value)
        if identity not in checks:
            if len(checks) >= 3:
                return False
            checks[identity] = asyncio.create_task(decide(request, key, value))
        return await checks[identity]

    return check
