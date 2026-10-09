"""Keep a read-to-listen switch behind committed agent element snapshots."""

from collections.abc import Iterator

import pytest
from flask import Flask
from flaskr.service.learn import runscript_v2 as runtime
from flaskr.service.learn.agent import lesson_entry
from flaskr.service.learn.learn_dtos import (
    ElementDTO,
    ElementType,
    GeneratedType,
    RunElementSSEMessageDTO,
    RunMarkdownFlowDTO,
)


@pytest.fixture
def execution(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stage final snapshots when the adapter receives the agent's last event."""
    from flaskr.service.learn.agent import preview_history

    monkeypatch.setattr(
        preview_history, "begin_preview_run", lambda *_a, **_k: "generation"
    )
    monkeypatch.setattr(
        preview_history, "pending_preview_record", lambda *_a, **_k: None
    )
    monkeypatch.setattr(preview_history, "preview_status_event", lambda *_a, **_k: None)
    sequence = []
    staged = []
    monkeypatch.setattr(runtime, "uses_agent_engine", lambda _bid: True)
    monkeypatch.setattr(
        runtime, "_commit_pending_step", lambda: sequence.append("commit")
    )
    raw = RunMarkdownFlowDTO(
        outline_bid="lesson",
        generated_block_bid="block",
        type=GeneratedType.DONE,
        content="",
    )
    monkeypatch.setattr(
        lesson_entry, "agent_lesson_events", lambda *_a, **_k: iter([raw])
    )
    final = RunElementSSEMessageDTO(
        type="element",
        event_type="element",
        generated_block_bid="block",
        content=ElementDTO(
            element_bid="question-text",
            generated_block_bid="block",
            element_index=0,
            role="teacher",
            element_type=ElementType.TEXT,
            element_type_code=0,
            content="Choose a path",
            is_speakable=True,
            is_final=True,
        ),
    )
    done = RunElementSSEMessageDTO(
        type="done",
        event_type="done",
        generated_block_bid="block",
        content="",
        is_terminal=True,
    )

    class Adapter:
        run_session_bid = "preview-run"

        def finalized_element_identities(self) -> list[tuple[str, str]]:
            return [("block", bid) for bid in staged]

        def process(self, events: Iterator) -> Iterator:
            for event in events:
                assert event is raw
                staged.append("question-text")
                yield final
                yield done

    return {"sequence": sequence, "staged": staged, "adapter": Adapter(), "done": done}


def _events(execution: dict, **overrides: object) -> Iterator:
    """Exercise the routed agent path with the same adapter the producer owns."""
    return runtime._lesson_events(
        **{
            "app": Flask(__name__),
            "user_bid": "learner",
            "shifu_bid": "course",
            "outline_bid": "lesson",
            "user_input": None,
            "input_type": None,
            "reload_generated_block_bid": None,
            "reload_element_bid": None,
            "listen": False,
            "learning_mode": "read",
            "preview_mode": False,
            "stop_event": None,
            "element_adapter": execution["adapter"],
            "heartbeat_interval": 0.5,
            **overrides,
        }
    )


@pytest.mark.parametrize(
    ("listen", "preview"), [(False, False), (True, False), (False, True)]
)
def test_agent_snapshots_commit_before_backfill_ready_and_terminal_done(
    execution: dict,
    listen: bool,
    preview: bool,
) -> None:
    """The browser stops on terminal done, so readiness must arrive first."""
    events = _events(execution, listen=listen, preview_mode=preview)
    first = next(events)
    assert first.type == "element"
    assert execution["staged"] == ["question-text"]
    assert execution["sequence"] == []
    ready = next(events)
    assert execution["sequence"] == ["commit"]
    assert ready.type == "audio_backfill_ready"
    assert ready.content.generated_block_bid == "block"
    assert ready.content.element_bids == ["question-text"]
    assert next(events) is execution["done"]
    assert list(events) == []


def test_failed_agent_snapshot_commit_emits_neither_ready_nor_terminal_success(
    execution: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An uncommitted element cannot be requested through the TTS endpoint."""

    def fail_commit() -> None:
        message = "commit failed"
        raise RuntimeError(message)

    monkeypatch.setattr(runtime, "_commit_pending_step", fail_commit)
    events = _events(execution)
    assert next(events).type == "element"
    with pytest.raises(RuntimeError, match="commit failed"):
        next(events)


def test_disconnected_agent_stream_never_advertises_uncommitted_audio(
    execution: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing before the final checkpoint leaves readiness unpublished."""
    closed = []

    def agent(*_args: object, **_kwargs: object) -> Iterator:
        try:
            yield RunMarkdownFlowDTO(
                outline_bid="lesson",
                generated_block_bid="block",
                type=GeneratedType.CONTENT,
                content="Choose a path",
            )
        finally:
            closed.append(True)

    class Adapter:
        def process(self, events: Iterator) -> Iterator:
            for _event in events:
                yield RunElementSSEMessageDTO(
                    type="element", event_type="element", content="partial"
                )

    execution["adapter"] = Adapter()
    monkeypatch.setattr(lesson_entry, "agent_lesson_events", agent)
    events = _events(execution)
    assert next(events).type == "element"
    events.close()
    assert execution["sequence"] == []
    assert closed == [True]


@pytest.mark.parametrize("with_interaction", [False, True])
@pytest.mark.parametrize("formatted", [False, True])
def test_real_adapter_finalizes_read_narration_before_advertising_backfill(
    execution: dict,
    monkeypatch: pytest.MonkeyPatch,
    with_interaction: bool,
    formatted: bool,
) -> None:
    """Partial read text becomes ready only after DONE has staged its final snapshot."""
    from flaskr.service.learn.listen_element_run_state import BlockMeta
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter

    adapter = ListenElementRunAdapter(
        Flask(__name__),
        shifu_bid="course",
        outline_bid="lesson",
        user_bid="learner",
        persist_only_final=True,
    )
    rows = []
    monkeypatch.setattr(adapter, "_load_block_meta", lambda _bid: BlockMeta())
    monkeypatch.setattr(adapter, "_deactivate_active_element_rows", lambda **_kw: None)
    monkeypatch.setattr(adapter, "_insert_row", lambda **row: rows.append(row))
    monkeypatch.setattr(
        "flaskr.service.learn.listen_element_run_sidecar._load_interaction_user_input",
        lambda _bid: None,
    )
    execution["adapter"] = adapter
    raw = [
        RunMarkdownFlowDTO(
            outline_bid="lesson", generated_block_bid="block", type=kind, content=text
        )
        for kind, text in [
            (GeneratedType.CONTENT, "Choose a path"),
            (GeneratedType.INTERACTION, "?[%{{path}} A | B]"),
            (GeneratedType.DONE, ""),
        ]
    ]
    if formatted:
        raw[0].set_mdflow_stream_parts([("Choose a path", "text", 0)])
    if not with_interaction:
        raw.pop(1)
    else:
        raw.insert(
            1,
            RunMarkdownFlowDTO(
                outline_bid="lesson",
                generated_block_bid="block",
                type=GeneratedType.BREAK,
                content="",
            ),
        )
    monkeypatch.setattr(
        lesson_entry, "agent_lesson_events", lambda *_a, **_k: iter(raw)
    )
    events = _events(execution)
    streamed = []
    with adapter.app.app_context():
        for event in events:
            if event.type == "audio_backfill_ready":
                assert execution["sequence"] == ["commit"]
                staged_bids = {
                    row["element_bid"] for row in rows if row["event_type"] == "element"
                }
                ready_bids = set(event.content.element_bids)
                assert ready_bids == staged_bids
                speakable_bids = {
                    row["element_bid"]
                    for row in rows
                    if row.get("is_speakable") and row.get("is_final")
                }
                assert speakable_bids
                assert speakable_bids <= ready_bids
            streamed.append(event)
    assert [event.type for event in streamed][-2:] == ["audio_backfill_ready", "done"]
    assert streamed[-1].is_terminal is True
    assert len(rows) == len(
        {(row["event_type"], row.get("element_bid")) for row in rows}
    )


@pytest.mark.parametrize("formatted", [False, True])
def test_budget_failure_commits_partial_elements_without_success_or_completion(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    formatted: bool,
) -> None:
    from uuid import uuid4

    from flaskr.dao import db
    from flaskr.service.common.models import ERROR_CODE, AppError
    from flaskr.service.learn.listen_element_run_state import BlockMeta
    from flaskr.service.learn.listen_elements import ListenElementRunAdapter
    from flaskr.service.learn.models import LearnGeneratedElement

    identity = uuid4().hex
    adapter = ListenElementRunAdapter(
        app,
        shifu_bid=identity,
        outline_bid=identity,
        user_bid=identity,
        persist_only_final=True,
    )
    monkeypatch.setattr(adapter, "_load_block_meta", lambda _bid: BlockMeta())
    monkeypatch.setattr(runtime, "uses_agent_engine", lambda _bid: True)
    failure = AppError(
        "Input capacity exceeded", ERROR_CODE["server.learn.agentInputBudgetExceeded"]
    )

    def agent(*_args: object, **_kwargs: object) -> Iterator:
        raw = RunMarkdownFlowDTO(
            outline_bid=identity,
            generated_block_bid=identity,
            type=GeneratedType.CONTENT,
            content="Step one remains visible.\n",
        )
        if formatted:
            raw.set_mdflow_stream_parts([("Step one remains visible.\n", "text", 0)])
        yield raw
        raise failure

    monkeypatch.setattr(lesson_entry, "agent_lesson_events", agent)
    streamed = []
    with app.app_context():
        with pytest.raises(AppError) as exc:
            streamed.extend(_events({"adapter": adapter}, app=app))
        assert exc.value is failure
        assert not any(
            event.type in {"done", "audio_backfill_ready"} for event in streamed
        )
        db.session.remove()
        rows = LearnGeneratedElement.query.filter_by(
            user_bid=identity, status=1, event_type="element"
        ).all()
        assert rows
        assert any("Step one remains visible." in row.content_text for row in rows)
        assert all(row.is_final for row in rows)
