"""Patches on a split learn module must reach the sibling that now uses the name."""

import pytest
from flaskr.service.learn import (
    live_follow_up_payloads,
    live_follow_up_routes,
    runscript_v2,
    runscript_v2_events,
    runscript_v2_stream,
)
from flaskr.service.learn.agent import run_agent, run_agent_delivery


def test_live_route_patch_reaches_payload_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = live_follow_up_payloads.to_utc_iso
    sentinel = object()

    monkeypatch.setattr(live_follow_up_routes, "to_utc_iso", sentinel)
    assert live_follow_up_payloads.to_utc_iso is sentinel

    monkeypatch.setattr(live_follow_up_routes, "_MAX_DIRECT_TURN_REPORT_BYTES", 7)
    assert live_follow_up_payloads._MAX_DIRECT_TURN_REPORT_BYTES == 7

    monkeypatch.undo()
    assert live_follow_up_payloads.to_utc_iso is original


def test_runscript_patch_reaches_stream_and_event_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()

    monkeypatch.setattr(runscript_v2, "_to_sse_chunk", sentinel)

    assert runscript_v2_events._to_sse_chunk is sentinel
    assert runscript_v2_stream._to_sse_chunk is sentinel


def test_run_agent_patch_reaches_delivery_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()

    monkeypatch.setattr(run_agent, "translate", sentinel)

    assert run_agent_delivery.translate is sentinel
