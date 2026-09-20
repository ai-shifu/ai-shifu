"""Find out whether a model can actually run a 2.0 lesson, by asking it to.

A 2.0 lesson is delivered through tool calls: the engine gives the model an `interact` tool and
stops when it calls it. A model that cannot call tools cannot teach a lesson at all -- it writes
the question as prose, and the learner never sees the controls to answer it.

Whether a model can is not something to look up. `litellm.supports_function_calling` answers
`False` for every model this deployment routes through its own gateway -- `ark/...`, `qwen/...`
-- because it does not recognise the routing names, while those models do call tools; believing
it would refuse the models that are actually in use. So this asks the model to call one and sees
what comes back, through the same gateway and the same arguments a lesson goes through.

Run before putting a course on the 2.0 allowlist:

    flask console agent check-model ark/deepseek-v4-1-flash-260910
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.api.llm import chat_llm

if TYPE_CHECKING:
    from flask import Flask

# Small, unambiguous, and answerable only by calling the tool.
_PROBE_MESSAGES = [
    {
        "role": "system",
        "content": (
            "You run a lesson. When you need something from the learner you must call the "
            "`interact` tool; never write the options as text."
        ),
    },
    {"role": "user", "content": "Ask the learner whether to continue."},
]

# The same shape `map_tools` builds for a real turn.
_PROBE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "interact",
            "description": "Show an interaction to the learner and wait for the answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["confirm"]},
                    "prompt": {"type": "string"},
                },
                "required": ["type", "prompt"],
            },
        },
    }
]


@dataclass(frozen=True)
class ModelCapability:
    """What a probe found out about one model."""

    model: str
    calls_tools: bool
    detail: str

    @property
    def can_teach(self) -> bool:
        """Whether a 2.0 lesson can be taught with this model."""
        return self.calls_tools


def probe_model(app: Flask, model: str, *, user_bid: str = "") -> ModelCapability:
    """Ask the model to call a tool, and report whether it did.

    A failure is an answer too: a model that cannot be reached, or that rejects a request
    carrying tools, cannot teach a lesson either, and the detail says which it was.
    """
    trace, span = create_trace_with_root_span(
        client=get_langfuse_client(),
        trace_payload={"name": "agent_model_probe", "metadata": {"model": model}},
        root_span_payload={"name": "agent_model_probe"},
    )
    # Arguments arrive in fragments, stitched back together by index -- a fragment on its own
    # says the model started a call, not that it produced one that works.
    fragments: dict[object, dict[str, str]] = {}
    finish_reason = ""
    failure = ""
    try:
        for chunk in chat_llm(
            app=app,
            user_id=user_bid,
            span=span,
            model=model,
            messages=_PROBE_MESSAGES,
            generation_name="agent_model_probe",
            emit_tool_calls=True,
            temperature=0,
            tools=_PROBE_TOOLS,
        ):
            for delta in getattr(chunk, "tool_call_deltas", None) or []:
                call = fragments.setdefault(
                    delta.get("index"), {"name": "", "arguments": ""}
                )
                call["name"] = call["name"] or (delta.get("name") or "")
                call["arguments"] += delta.get("arguments") or ""
            reason = getattr(chunk, "finish_reason", "") or ""
            if reason:
                finish_reason = str(reason)
    except Exception as exc:
        failure = f"the gateway call failed: {type(exc).__name__}: {exc}"
    finally:
        finalize_langfuse_trace(trace=trace, root_span=span)

    if failure:
        return ModelCapability(model=model, calls_tools=False, detail=failure)

    usable = [
        call
        for call in fragments.values()
        if call["name"] == "interact" and _has_question(call["arguments"])
    ]
    if usable:
        return ModelCapability(
            model=model, calls_tools=True, detail="called the tool it was given"
        )
    if fragments or finish_reason == "tool_calls":
        # It reached for a tool and did not come back with one that works: a call for something
        # other than `interact`, arguments that do not parse, or a stop reason saying it called
        # while nothing arrived. Reported apart from an answer in prose, because the two are
        # fixed in different places.
        names = sorted({call["name"] for call in fragments.values() if call["name"]})
        return ModelCapability(
            model=model,
            calls_tools=False,
            detail=(
                "started a tool call it did not complete"
                + (f" (called {', '.join(names)})" if names else "")
                + (f" (stopped on {finish_reason})" if finish_reason else "")
            ),
        )
    return ModelCapability(
        model=model,
        calls_tools=False,
        detail=(
            "answered without calling the tool"
            + (f" (stopped on {finish_reason})" if finish_reason else "")
        ),
    )


def _has_question(arguments: str) -> bool:
    """Whether the assembled arguments parse and carry the question to ask.

    Only that much: a model that fills the rest in differently than the engine would has still
    called the tool, and refusing it here would repeat the mistake this probe exists to avoid --
    deciding from a rule about the model rather than from what it did.
    """
    try:
        parsed = json.loads(arguments or "")
    except ValueError:
        return False
    return isinstance(parsed, dict) and bool(parsed.get("prompt"))
