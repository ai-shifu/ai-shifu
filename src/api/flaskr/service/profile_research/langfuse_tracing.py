"""Keep Profile-specific Langfuse presentation outside questionnaire orchestration."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING

from flaskr.api.langfuse_markdownflow import MarkdownFlowTrace
from flaskr.service.profile_research.session import PROFILE_ONBOARDING_PREVIEW_PURPOSE

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Mapping

    from flaskr.api.langfuse_markdownflow import SafeObservation
    from flaskr.service.profile_research.session import _ProfileResearchSession

PROFILE_GENERATION_NAME = "profile.generate"
PROFILE_PRIVATE_GENERATION_NAME = "profile.model"


class ProfileTrace(MarkdownFlowTrace):
    """Present one admitted Profile operation and its persisted public result."""

    def __init__(
        self,
        session: _ProfileResearchSession,
        submitted_input: object = None,
        *,
        operation: str = "run",
    ) -> None:
        """Bind the exact questionnaire and action before invoking any model."""
        scene = (
            "profile-preview"
            if session.purpose == PROFILE_ONBOARDING_PREVIEW_PURPOSE
            else "profile"
        )
        super().__init__(
            name=scene,
            user_id=session.user_bid,
            input=submitted_input
            or {"action": "continue" if session.engine_session else "start"},
            session_id=session.session_id,
            metadata={
                "scene": scene,
                "purpose": session.purpose,
                "config_revision": session.config_revision,
                "turn_index": session.turn_index,
                "operation": operation,
            },
        )
        self._operation = operation
        self.set_context(
            session_id=session.session_id,
            script=session.document,
            metadata={"config_revision": session.config_revision},
        )
        self.start_turn(metadata={"turn_index": session.turn_index})

    def publish(
        self,
        session: _ProfileResearchSession,
        events: Iterable[Mapping[str, object]],
    ) -> None:
        """Record validated public output only after its atomic save succeeded."""
        # Profile stream text is cumulative per element. The terminal payload's
        # private draft belongs only in its transformation child observation.
        previous: dict[tuple[str, str], str] = {}
        has_visible_output = False
        for event in events:
            if event.get("type") not in {"content", "interaction"}:
                continue
            value = event.get("content")
            if not isinstance(value, str) or not value:
                continue
            key = (str(event["type"]), str(event.get("generated_block_bid") or ""))
            earlier = previous.get(key, "")
            self.append_output(value.removeprefix(earlier))
            has_visible_output = has_visible_output or bool(value.strip())
            previous[key] = value
        if not has_visible_output:
            status = (
                {"done": session.done, "operation": "delegate"}
                if self._operation == "delegate"
                else {"done": session.done, "awaiting_input": session.awaiting_input}
            )
            self.append_output(json.dumps(status))
        self.complete_turn(
            "finished"
            if session.done
            else "waiting"
            if session.awaiting_input
            else "end"
        )

    @contextlib.contextmanager
    def step(
        self, name: str, input_value: object
    ) -> Generator[SafeObservation, None, None]:
        """Capture one private transformation's real input, output and failure."""
        step = self.child(name, input=input_value)
        try:
            yield step
        except Exception as exc:
            step.end(level="ERROR", status_message=type(exc).__name__)
            raise
        else:
            step.end()

    @classmethod
    @contextlib.contextmanager
    def _private_step(
        cls,
        session: _ProfileResearchSession,
        name: str,
        input_value: object,
        *,
        operation: str,
        trace: ProfileTrace | None,
    ) -> Generator[SafeObservation, None, None]:
        request_input = {"action": "summary"} if operation == "summary" else input_value
        active = trace or cls(session, request_input, operation=operation)
        with (
            active if trace is None else contextlib.nullcontext(),
            active.step(name, input_value) as step,
        ):
            yield step

    @classmethod
    def summary(
        cls,
        session: _ProfileResearchSession,
        messages: object,
        *,
        trace: ProfileTrace | None = None,
    ) -> contextlib.AbstractContextManager[SafeObservation]:
        """Nest summaries under an existing request, or own a standalone helper call."""
        return cls._private_step(
            session, "profile.summary", messages, operation="summary", trace=trace
        )

    @classmethod
    def import_answers(
        cls,
        session: _ProfileResearchSession,
        raw_text: str,
        *,
        trace: ProfileTrace | None = None,
    ) -> contextlib.AbstractContextManager[SafeObservation]:
        """Nest answer extraction without exposing private results on the request root."""
        return cls._private_step(
            session, "profile.import", raw_text, operation="delegate", trace=trace
        )
