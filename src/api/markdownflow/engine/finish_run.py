"""End a completed lesson after its current batch of tools has settled."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from pydantic_ai import CallToolsNode, ModelRequestNode
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import RetryPromptPart
from pydantic_ai.result import FinalResult
from pydantic_graph import End

from .tools import Deps

if TYPE_CHECKING:
    from pydantic_ai import RunContext
    from pydantic_ai.capabilities.abstract import AgentNode, NodeResult


class FinishAfterTools(AbstractCapability[Deps]):
    """Keep tool results and pending questions without requesting a farewell."""

    async def after_node_run(
        self,
        ctx: RunContext[Deps],
        *,
        node: AgentNode[Deps],
        result: NodeResult[Deps],
    ) -> NodeResult[Deps]:
        """Replace only a successful finish's next model request with a result."""
        if (
            not isinstance(node, CallToolsNode)
            or not isinstance(result, ModelRequestNode)
            or ctx.deps.finished is None
            or any(isinstance(part, RetryPromptPart) for part in result.request.parts)
        ):
            # Deferred questions already produce their own result. A rejected
            # sibling tool still needs its retry, even if finish succeeded.
            return result

        # Match the SDK's normal final-result history: retain the whole batch
        # of tool returns, including finish, so reloads have no dangling calls.
        ctx.messages.append(
            replace(
                result.request,
                run_id=ctx.run_id,
                conversation_id=ctx.conversation_id,
            )
        )
        return End(FinalResult(ctx.deps.finished))
