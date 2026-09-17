"""Event payloads: what the host sees on the wire for each engine event."""

import json

from flaskr.service.learn.agent.engine import (
    ContentDelta,
    InteractionRequest,
    InteractionSpec,
    Option,
    TurnDone,
    parse_event,
    to_sse,
)


def test_sse_roundtrip() -> None:
    ev = InteractionRequest(
        id="c1",
        spec=InteractionSpec(type="single", prompt="q", options=[Option(display="A")]),
    )
    frame = to_sse(ev)
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    back = parse_event(frame[len("data: ") :].strip())
    assert back == ev


def test_parse_by_discriminator() -> None:
    assert isinstance(parse_event({"type": "content.delta", "text": "x"}), ContentDelta)
    assert isinstance(
        parse_event(json.dumps({"type": "turn.done", "reason": "end"})), TurnDone
    )
