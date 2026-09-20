"""The engine: builds the agent, runs one turn, yields events."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    DeferredToolRequests,
    DeferredToolResults,
    RunContext,
    Tool,
    UsageLimits,
)
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable, Sequence

    from pydantic_ai.models import Model
    from pydantic_ai.settings import ModelSettings
    from pydantic_ai.toolsets import AbstractToolset

    from .memory import MemoryStore
    from .session import SessionStore

from .events import (
    ContentDelta,
    ErrorEvent,
    Event,
    InteractionRequest,
    MemoryUpdated,
    NarrationDelta,
    SegmentEnd,
    SegmentStart,
    ToolCall,
    ToolResult,
    TurnDone,
)
from .interaction import (
    InteractionAnswer,
    InteractionSpec,
    answer_is_usable,
    format_answer_for_model,
    normalize_answer,
    stored_value,
)
from .script import ScriptBundle, detect_v1_syntax, render_first_prompt
from .segmenter import Narration, Segmenter, SegmentPiece
from .session import PendingInteraction, Session
from .tools import Deps, finish, interact, remember

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
PROMPTS_DIR = Path(__file__).parent / "prompts"
RenderProfile = Literal["sandbox", "generic", "none"]


# -- turn inputs ---------------------------------------------------------------------------


class StartTurn(BaseModel):
    """Begin the lesson."""

    type: Literal["start"] = "start"


class ContinueTurn(BaseModel):
    """Carry on without the learner saying anything."""

    type: Literal["continue"] = "continue"


class MessageTurn(BaseModel):
    """Free text from the learner: a side question, a request, an unsolicited answer."""

    type: Literal["message"] = "message"
    text: str


class InteractionResponseTurn(BaseModel):
    """The learner's answer to a pending interaction."""

    type: Literal["interaction.response"] = "interaction.response"
    id: str | None = (
        None  # tool_call_id of the pending interaction; None = the only pending one
    )
    values: list[str] = []
    text: str | None = None

    def answer(self) -> InteractionAnswer:
        """Build the learner's submission as an InteractionAnswer."""
        return InteractionAnswer(values=list(self.values), text=self.text)


TurnInput = StartTurn | ContinueTurn | MessageTurn | InteractionResponseTurn


@dataclass
class Prompts:
    """The instruction fragments the engine composes into one system message."""

    base: str
    listen_mode: str
    v1_syntax: str
    html_display: str = ""
    html_display_generic: str = ""

    @classmethod
    def default(cls) -> Prompts:
        """Load the instruction fragments that ship with the engine."""
        return cls(
            base=(PROMPTS_DIR / "system.md").read_text(),
            listen_mode=(PROMPTS_DIR / "listen_mode.md").read_text(),
            v1_syntax=(PROMPTS_DIR / "v1_syntax.md").read_text(),
            html_display=(PROMPTS_DIR / "html_display.md").read_text(),
            html_display_generic=(PROMPTS_DIR / "html_display_generic.md").read_text(),
        )


class Engine:
    """One engine per model/config; sessions are passed in per turn."""

    def __init__(
        self,
        model: Model | str,
        *,
        prompts: Prompts | None = None,
        extra_instructions: str | None = None,
        toolsets: Sequence[AbstractToolset[Deps]] | None = None,
        memory_store: MemoryStore | None = None,
        render: RenderProfile = "sandbox",
        request_limit: int = 12,
        tool_calls_limit: int | None = 30,
        turn_limit: int = 200,
        model_settings: ModelSettings | None = None,
    ) -> None:
        """Bind a model and the host's capabilities; sessions are supplied per turn."""
        self.prompts = prompts or Prompts.default()
        self.extra_instructions = extra_instructions
        self.render: RenderProfile = render
        self.memory_store = memory_store
        self.limits = UsageLimits(
            request_limit=request_limit, tool_calls_limit=tool_calls_limit
        )
        # A backstop, not a teaching limit. The model often never calls `finish`, so nothing else
        # ends a lesson that has run out of script: the learner keeps continuing and the session
        # keeps growing, one model call at a time. The longest real lesson in production runs to
        # 138 blocks, and a 2.0 turn covers roughly one block, so this sits far above any lesson
        # anyone writes -- reaching it means the lesson is going in circles, not that it is long.
        self.turn_limit = turn_limit
        self.agent: Agent[Deps, str | DeferredToolRequests] = Agent(
            model,
            deps_type=Deps,
            output_type=[str, DeferredToolRequests],
            instructions=self._instructions,
            tools=[Tool(interact, max_retries=2), remember, finish],
            toolsets=list(toolsets or []),
            model_settings=model_settings,
        )

    def compose_instructions(
        self,
        *,
        listen_mode: bool = False,
        uses_v1_syntax: bool = False,
        render: RenderProfile = "sandbox",
    ) -> str:
        """Build the single system message for a given host capability set.

        `render` says how the host shows HTML: `sandbox` (this project's UI, with Tailwind,
        DaisyUI and GSAP preloaded), `generic` (any assistant that can show plain HTML), or
        `none` (text only).
        """
        parts = [self.prompts.base]
        if render == "sandbox":
            parts.append(self.prompts.html_display)
        elif render == "generic":
            parts.append(self.prompts.html_display_generic)
        if listen_mode:
            parts.append(self.prompts.listen_mode)
        if uses_v1_syntax:
            parts.append(self.prompts.v1_syntax)
        if self.extra_instructions:
            parts.append(self.extra_instructions)
        return "\n\n".join(p.strip() for p in parts if p and p.strip())

    def _instructions(self, ctx: RunContext[Deps]) -> str:
        return self.compose_instructions(
            listen_mode=ctx.deps.listen_mode,
            uses_v1_syntax=ctx.deps.uses_v1_syntax,
            render=self.render,
        )

    # -- sessions ----------------------------------------------------------------------------

    async def new_session(
        self,
        script: ScriptBundle | str,
        *,
        user_id: str | None = None,
        memory: dict[str, Any] | None = None,
        listen_mode: bool = False,
    ) -> Session:
        """Start a session for a script, seeded with what is already known about the learner."""
        bundle = (
            script if isinstance(script, ScriptBundle) else ScriptBundle(script=script)
        )
        user_memory: dict[str, Any] = {}
        if user_id and self.memory_store is not None:
            user_memory = await self.memory_store.load(user_id)
        return Session(
            script=bundle,
            user_id=user_id,
            listen_mode=listen_mode,
            memory=dict(memory or {}),
            user_memory=user_memory,
        )

    # -- turns -------------------------------------------------------------------------------

    async def run_turn(
        self, session: Session, turn: TurnInput | None = None
    ) -> AsyncIterator[Event]:
        """Run one turn of a session and stream its events.

        One `Engine` serves any number of sessions concurrently: the model, prompts and tools on
        it are read-only, and everything that changes lives on the `Session`.

        A single `Session` is not concurrency-safe. Two overlapping `run_turn` calls on the same
        session both pass the pending check, both call the model, and leave duplicated pending
        interactions behind, so the host must serialize turns per session -- a learner with the
        lesson open in two tabs is the case that matters.
        """
        if session.finished:
            # Terminal: a repeated or late request must not run the model on a finished lesson.
            yield TurnDone(reason="finished", usage=session.usage)
            return
        turn = turn or (StartTurn() if not session.started else ContinueTurn())
        deps = Deps(
            memory=session.memory,
            user_memory=session.user_memory,
            listen_mode=session.listen_mode,
            uses_v1_syntax=detect_v1_syntax(session.script.all_text()),
        )
        deps.history_len = len(session.messages) if session.started else 0
        kwargs: dict[str, Any] = {"deps": deps, "usage_limits": self.limits}
        resumed: set[str] = set()
        prompt: str | None

        if not session.started:
            if isinstance(turn, InteractionResponseTurn):
                yield ErrorEvent(message="no interaction is pending on a new session")
                return
            prompt = render_first_prompt(session.script, session.all_memory())
            if isinstance(turn, MessageTurn):
                prompt += f"\n\n{turn.text}"
        elif session.pending:
            if not isinstance(turn, InteractionResponseTurn):
                yield ErrorEvent(
                    message="an interaction is pending; send interaction.response"
                )
                return
            pending = self._pick_pending(session, turn.id)
            if pending is None:
                yield ErrorEvent(message=f"unknown interaction id {turn.id!r}")
                return
            answer = normalize_answer(pending.spec, turn.answer())
            if not answer_is_usable(pending.spec, answer):
                # Resuming here would hand the model "continued without answering" and let a
                # question the script requires be skipped, so keep it pending and ask again.
                yield ErrorEvent(
                    message=f"interaction {pending.tool_call_id!r} needs an answer",
                    retryable=True,
                )
                yield InteractionRequest(id=pending.tool_call_id, spec=pending.spec)
                yield TurnDone(reason="interaction", usage=session.usage)
                return
            session.answers[pending.tool_call_id] = format_answer_for_model(
                pending.spec, answer
            )
            if pending.spec.variable:
                value = stored_value(pending.spec, answer)
                if value is not None:
                    session.memory[pending.spec.variable] = value
                    yield MemoryUpdated(
                        key=pending.spec.variable, value=value, source="interaction"
                    )
            session.pending = [
                p for p in session.pending if p.tool_call_id != pending.tool_call_id
            ]
            if session.pending:
                # The model raised several interactions in one turn. Ask the next one and wait:
                # pydantic-ai rejects a resume that leaves any deferred call unanswered, so the
                # model only runs again once every one of them has an answer.
                nxt = session.pending[0]
                yield InteractionRequest(id=nxt.tool_call_id, spec=nxt.spec)
                yield TurnDone(reason="interaction", usage=session.usage)
                return
            kwargs["deferred_tool_results"] = DeferredToolResults(
                calls=dict(session.answers)
            )
            resumed.update(session.answers)
            prompt = None
        elif session.answers:
            # A previous resume never reached the model (a network error, a rate limit). The
            # answers are still here, so send them again. Without this the unanswered deferred
            # call stays in the history and every later turn fails on it, with no interaction
            # left to show the learner -- stuck for good.
            kwargs["deferred_tool_results"] = DeferredToolResults(
                calls=dict(session.answers)
            )
            resumed.update(session.answers)
            prompt = None
        else:
            if isinstance(turn, InteractionResponseTurn):
                yield ErrorEvent(message="no interaction is pending")
                return
            prompt = turn.text if isinstance(turn, MessageTurn) else "continue"
        if prompt is not None and self.turn_limit and session.turn >= self.turn_limit:
            # Out of turns: end the lesson rather than teach another one. Marked finished so a
            # reload does not start it over, and reported as finished rather than as an error --
            # everything the learner was taught stands, and the host reads this as a lesson that
            # is over.
            #
            # Only a new turn of teaching is refused. A `prompt` of None means this call is
            # finishing something already begun: the learner answering the question the last turn
            # asked, or a resume that never reached the model. Refusing those would throw away an
            # answer the script requires -- along with the memory it sets -- and would turn one
            # network failure on the last turn into a lesson that can never be continued.
            session.finished = True
            yield TurnDone(reason="finished", usage=session.usage)
            return

        if session.started:
            kwargs["message_history"] = session.messages

        segmenter = Segmenter() if session.listen_mode else None
        seg_state: dict[str, Any] = {"n": 0, "id": None, "narration": []}
        session.turn += 1

        try:
            async with self.agent.run_stream_events(prompt, **kwargs) as events:
                async for ev in events:
                    if isinstance(ev, PartStartEvent) and isinstance(ev.part, TextPart):
                        if ev.part.content:
                            yield ContentDelta(text=ev.part.content)
                            if segmenter:
                                for e in self._segment(
                                    segmenter.feed(ev.part.content), seg_state, session
                                ):
                                    yield e
                    elif isinstance(ev, PartDeltaEvent) and isinstance(
                        ev.delta, TextPartDelta
                    ):
                        yield ContentDelta(text=ev.delta.content_delta)
                        if segmenter:
                            for e in self._segment(
                                segmenter.feed(ev.delta.content_delta),
                                seg_state,
                                session,
                            ):
                                yield e
                    elif isinstance(ev, FunctionToolCallEvent):
                        if ev.part.tool_call_id in resumed:
                            continue
                        yield ToolCall(
                            id=ev.part.tool_call_id,
                            name=ev.part.tool_name,
                            args=ev.part.args_as_dict(),
                        )
                    elif isinstance(ev, FunctionToolResultEvent):
                        if ev.part.tool_call_id in resumed:
                            continue
                        if ev.part.tool_name == "finish":
                            continue
                        if ev.part.tool_name == "remember":
                            while deps.memory_updates:
                                scope, key, value = deps.memory_updates.pop(0)
                                yield MemoryUpdated(
                                    key=key, value=value, scope=scope, source="tool"
                                )
                        else:
                            yield ToolResult(
                                id=ev.part.tool_call_id,
                                name=ev.part.tool_name or "",
                                content=getattr(ev.part, "content", None),
                            )
                    elif isinstance(ev, AgentRunResultEvent):
                        result = ev.result
                        session.messages = list(result.all_messages())
                        # Only now are the answers safely part of the history; clearing them any
                        # earlier would lose them if the request failed.
                        session.answers = {}
                        u = result.usage
                        session.usage = {
                            "requests": session.usage.get("requests", 0) + u.requests,
                            "input_tokens": session.usage.get("input_tokens", 0)
                            + u.input_tokens,
                            "output_tokens": session.usage.get("output_tokens", 0)
                            + u.output_tokens,
                        }
                        if segmenter:
                            for e in self._segment(
                                segmenter.finish(), seg_state, session, final=True
                            ):
                                yield e
                        if isinstance(result.output, DeferredToolRequests):
                            for call in result.output.calls:
                                spec = InteractionSpec.model_validate(
                                    result.output.metadata.get(call.tool_call_id, {})
                                )
                                session.pending.append(
                                    PendingInteraction(call.tool_call_id, spec)
                                )
                                yield InteractionRequest(
                                    id=call.tool_call_id, spec=spec
                                )
                            yield TurnDone(reason="interaction", usage=session.usage)
                        elif deps.finished is not None:
                            session.finished = True
                            yield TurnDone(
                                reason="finished",
                                usage=session.usage,
                                summary=deps.finished,
                            )
                        else:
                            yield TurnDone(reason="end", usage=session.usage)
        # Surface any failure to the host and keep the session usable.
        except Exception as exc:
            yield ErrorEvent(message=f"{type(exc).__name__}: {exc}", retryable=True)
            return
        finally:
            if (
                session.user_id
                and self.memory_store is not None
                and (
                    any(scope == "user" for scope, _, _ in deps.memory_updates)
                    or session.user_memory
                )
            ):
                await self.memory_store.save(session.user_id, session.user_memory)

    @staticmethod
    def _pick_pending(
        session: Session, tool_call_id: str | None
    ) -> PendingInteraction | None:
        if tool_call_id is None:
            return session.pending[0] if session.pending else None
        return next(
            (p for p in session.pending if p.tool_call_id == tool_call_id), None
        )

    @staticmethod
    def _segment(
        pieces: Iterable[SegmentPiece],
        state: dict[str, Any],
        session: Session,
        final: bool = False,
    ) -> list[Event]:
        out: list[Event] = []
        for piece in pieces:
            if isinstance(piece, Narration):
                if state["id"] is None:
                    state["n"] += 1
                    state["id"] = f"{session.id[:8]}-{session.turn}-{state['n']}"
                    out.append(SegmentStart(segment_id=state["id"], visual=None))
                state["narration"].append(piece.text)
                out.append(NarrationDelta(segment_id=state["id"], text=piece.text))
            else:  # Visual opens a new segment
                if state["id"] is not None:
                    out.append(
                        SegmentEnd(
                            segment_id=state["id"],
                            narration="".join(state["narration"]),
                        )
                    )
                state["n"] += 1
                state["id"] = f"{session.id[:8]}-{session.turn}-{state['n']}"
                state["narration"] = []
                out.append(SegmentStart(segment_id=state["id"], visual=piece))
        if final and state["id"] is not None:
            out.append(
                SegmentEnd(
                    segment_id=state["id"], narration="".join(state["narration"])
                )
            )
            state["id"] = None
            state["narration"] = []
        return out


class Runner:
    """Engine + session store: the shape a host calls from an HTTP handler."""

    def __init__(self, engine: Engine, store: SessionStore) -> None:
        """Pair an engine with the store its sessions live in."""
        self.engine = engine
        self.store = store

    async def new_session(self, script: ScriptBundle | str, **kw: object) -> Session:
        """Start a session for a script, seeded with what is already known about the learner."""
        session = await self.engine.new_session(script, **kw)
        await self.store.save(session)
        return session

    async def run(
        self, session_id: str, turn: TurnInput | None = None
    ) -> AsyncIterator[Event]:
        """Run one turn for a stored session and save it afterwards."""
        session = await self.store.load(session_id)
        if session is None:
            yield ErrorEvent(message=f"unknown session {session_id!r}")
            return
        try:
            async for ev in self.engine.run_turn(session, turn):
                yield ev
        finally:
            await self.store.save(session)
