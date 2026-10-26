"""Best-effort Langfuse tracing for course teaching and Profile onboarding."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flaskr.api.langfuse import (
    MockClient,
    create_trace_with_root_span,
    get_langfuse_client,
    get_request_id,
    get_request_trace_id,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType
    from typing import Self

    from flaskr.api.markdownflow import Event

logger = logging.getLogger(__name__)


class SafeObservation:
    """Keep optional telemetry failures outside the gateway's business path."""

    def __init__(
        self,
        observation: object = None,
        *,
        observation_source: Callable[[], object] | None = None,
    ) -> None:
        """Wrap an optional observation without starting additional telemetry."""
        self._observation = observation if observation is not None else MockClient()
        self._observation_source = observation_source
        self._ended = False

    def _target(self) -> object:
        if self._observation_source is not None:
            return self._observation_source()
        return self._observation

    @property
    def trace_id(self) -> str:
        """Return a usable correlation id even when tracing is disabled."""
        value = getattr(self._target(), "trace_id", "")
        return value if isinstance(value, str) else ""

    @property
    def id(self) -> str:
        """Return the underlying observation identifier when present."""
        value = getattr(self._target(), "id", "")
        return value if isinstance(value, str) else ""

    def _call(self, method: str, **kwargs: object) -> object:
        try:
            return getattr(self._target(), method)(**kwargs)
        except Exception as error:
            logger.warning(
                "MarkdownFlow tracing operation failed: %s (%s)",
                method,
                type(error).__name__,
            )
            return MockClient()

    def observation(
        self, *, as_type: str = "span", **kwargs: object
    ) -> SafeObservation:
        """Create a safe typed child observation."""
        return SafeObservation(self._call("observation", as_type=as_type, **kwargs))

    def span(self, **kwargs: object) -> SafeObservation:
        """Create a safe child span."""
        return SafeObservation(self._call("span", **kwargs))

    def generation(self, **kwargs: object) -> SafeObservation:
        """Create a safe generation for the existing gateway."""
        return SafeObservation(self._call("generation", **kwargs))

    def event(self, **kwargs: object) -> SafeObservation:
        """Record a best-effort instantaneous event."""
        return SafeObservation(self._call("event", **kwargs))

    def update(self, **kwargs: object) -> SafeObservation:
        """Update an observation without affecting its caller on failure."""
        self._call("update", **kwargs)
        return self

    def update_trace(self, **kwargs: object) -> SafeObservation:
        """Update the underlying trace correlation attributes."""
        self._call("update_trace", **kwargs)
        return self

    def end(self, **kwargs: object) -> SafeObservation:
        """Finalize at most once, including when the SDK raises."""
        if not self._ended:
            self._ended = True
            self._call("end", **kwargs)
        return self


class MarkdownFlowTrace:
    """Own one request, with explicit parents across producer-thread boundaries."""

    def __init__(
        self,
        *,
        name: str,
        user_id: str,
        input: object,  # noqa: A002 - Match the Langfuse observation payload field.
        metadata: dict[str, object] | None = None,
        session_id: str | None = None,
    ) -> None:
        """Start the request root, falling back to no-op handles on SDK failure."""
        self._metadata = {
            **(metadata or {}),
            "flow_engine": "2.0",
            "request_id": get_request_id(),
        }
        try:
            trace, root = create_trace_with_root_span(
                client=get_langfuse_client(),
                trace_payload={
                    "id": get_request_trace_id(),
                    "name": name,
                    "user_id": user_id,
                    "session_id": session_id,
                    "input": input,
                    "metadata": self._metadata,
                },
                root_span_payload={"name": name},
            )
        except Exception as error:
            logger.warning(
                "MarkdownFlow trace creation failed (%s)", type(error).__name__
            )
            trace, root = MockClient(), MockClient()
        self._trace = SafeObservation(trace)
        self.root = SafeObservation(root)
        self.current = self.root
        # Gateway instances can be reused across turns. This permanent handle
        # resolves the explicit parent when a generation starts, on any thread.
        self.model_parent = SafeObservation(observation_source=lambda: self.current)
        self._turn: SafeObservation | None = None
        self._tools: dict[str, tuple[str, SafeObservation, dict[str, object]]] = {}
        self._output: list[str] = []
        self._turn_output_start = 0
        self._outcome = "running"
        self._finished = False
        self._context_identity: tuple[str, str, str] | None = None

    def __enter__(self) -> Self:
        """Keep request lifetime management inside the tracing integration."""
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Finalize tracing while propagating the original business exception."""
        if isinstance(error, GeneratorExit):
            self.finish(transport_closed=True)
        elif error is not None:
            self.root.update(status_message=type(error).__name__)
            self.finish("discarded" if self._outcome == "discarded" else "error")
        else:
            self.finish()

    def set_input(self, value: object) -> None:
        """Refine a no-text action after the host restores its native session."""
        self.root.update(input=value)

    def set_context(
        self,
        *,
        session_id: str,
        script: str,
        teaching_brief: str = "",
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Record the effective script separately from the learner's request."""
        self._trace.update(session_id=session_id, metadata=metadata or {})
        if self.current is not self.root:
            self.current.update_trace(session_id=session_id, metadata=metadata or {})
        identity = (session_id, script, teaching_brief)
        if identity == self._context_identity:
            return
        self._context_identity = identity
        self.child(
            "context",
            input={"script": script, "teaching_brief": teaching_brief},
            metadata=metadata,
        ).end(output={"loaded": True})

    def child(
        self,
        name: str,
        *,
        input: object = None,  # noqa: A002 - Match the Langfuse observation payload field.
        metadata: dict[str, object] | None = None,
        as_type: str = "span",
    ) -> SafeObservation:
        """Create a request-owned application step with a stable operation name."""
        return self.root.observation(
            as_type=as_type, name=name, input=input, metadata=metadata
        )

    def start_turn(
        self,
        *,
        metadata: dict[str, object] | None = None,
        input: object = None,  # noqa: A002 - Match the Langfuse observation payload field.
    ) -> SafeObservation:
        """Start the next agent turn beneath the same request root."""
        if self._turn is not None:
            self.complete_turn("end")
        self._outcome = "running"
        self._turn_output_start = len(self._output)
        self._turn = self.child("turn", as_type="agent", input=input, metadata=metadata)
        self.current = self._turn
        return self.current

    def append_output(self, value: str) -> None:
        """Collect only content the host has chosen to present publicly."""
        if isinstance(value, str) and value:
            self._output.append(value)

    def _end_tools(self, outcome: str) -> None:
        tools, self._tools = self._tools, {}
        for name, observation, _ in tools.values():
            status = (
                "waiting"
                if name == "interact" and outcome == "interaction"
                else outcome
            )
            if name == "remember" and outcome not in {"error", "disconnected"}:
                # The engine omits results for refused notes too; no update is not success.
                status = "result_unavailable"
            observation.end(output={"status": status}, metadata={"outcome": status})

    def event(self, event: Event) -> None:
        """Observe validated native events without changing execution or persistence."""
        try:
            self._event(event)
        except Exception as error:
            logger.warning("MarkdownFlow trace event failed (%s)", type(error).__name__)

    def _event(self, event: Event) -> None:
        kind = getattr(event, "type", "")
        if kind == "tool.call":
            previous = self._tools.pop(event.id, None)
            if previous is not None:
                previous[1].end(output={"status": "superseded"})
            self._tools[event.id] = (
                event.name,
                self.current.observation(
                    as_type="tool",
                    name=event.name,
                    input=event.args,
                    metadata={"tool_call_id": event.id},
                ),
                event.args,
            )
        elif kind == "tool.result":
            tool = self._tools.pop(event.id, None)
            if tool is not None:
                tool[1].end(output=event.content, metadata={"outcome": "completed"})
        elif kind == "interaction.request":
            tool = self._tools.pop(event.id, None)
            if tool is not None:
                tool[1].end(
                    output=event.spec.model_dump(mode="json"),
                    metadata={"outcome": "waiting"},
                )
        elif kind == "memory.updated":
            if event.source == "tool":
                for key, (name, observation, args) in tuple(self._tools.items()):
                    if (
                        name == "remember"
                        and str(args.get("key", "")).strip() == event.key
                    ):
                        self._tools.pop(key)
                        observation.end(
                            output={
                                "key": event.key,
                                "value": event.value,
                                "status": "staged",
                            },
                            metadata={"outcome": "staged"},
                        )
                        break
            self.current.event(
                name="memory",
                input={"key": event.key, "scope": event.scope, "source": event.source},
                output={"value": event.value, "status": "staged"},
            )
        elif kind == "error":
            self.current.event(
                name="error",
                level="WARNING" if event.retryable else "ERROR",
                status_message=event.code or "engine_error",
                metadata={"retryable": event.retryable},
            )
        # A native TurnDone is not a committed result. Unmatched tools stay
        # open until complete_turn receives the host's authoritative save outcome.

    def complete_turn(self, outcome: str) -> None:
        """Mark the host's committed outcome before its terminal event is yielded."""
        self._outcome = outcome
        self._end_tools(outcome)
        if self._turn is not None:
            self._turn.end(
                output="".join(self._output[self._turn_output_start :]),
                metadata={"outcome": outcome},
                level="ERROR" if outcome == "error" else "DEFAULT",
            )
            self._turn = None
        self.current = self.root

    def finish(
        self, outcome: str | None = None, *, transport_closed: bool = False
    ) -> None:
        """Close once, retaining committed success when the transport closes later."""
        if self._finished:
            return
        self._finished = True
        actual = outcome or self._outcome
        if transport_closed and actual in {"running", "end"}:
            actual = "disconnected"
        elif actual == "running":
            actual = "completed"
        self.complete_turn(actual)
        metadata = {
            "runtime_outcome": actual,
            "transport_closed": transport_closed,
            "end_reason": actual
            if actual in {"error", "disconnected"}
            else "completed",
        }
        self._trace.update(metadata=metadata)
        self.root.end(
            output="".join(self._output),
            metadata=metadata,
            level="ERROR" if actual == "error" else "DEFAULT",
        )
