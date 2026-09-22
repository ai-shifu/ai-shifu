"""Verify lesson resolution and cancellation at run-script step boundaries."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import runscript_v2 as run
from flaskr.service.learn.learn_dtos import GeneratedType, RunMarkdownFlowDTO


@pytest.fixture
def execution(monkeypatch: object) -> object:
    context = Mock()
    context.has_next.return_value = False
    context.reload.return_value = iter([])
    factory = Mock(return_value=context)

    class Context:
        def __new__(cls, **kwargs: object) -> object:
            return factory(**kwargs)

    monkeypatch.setattr(run, "RunScriptContextV2", Context)
    monkeypatch.setattr(run, "_ensure_healthy_db_connection", Mock())
    monkeypatch.setattr(
        run, "load_user_aggregate", lambda _: SimpleNamespace(user_id="learner")
    )
    course = SimpleNamespace(bid="resolved-course", price=0)
    course_loader = Mock(return_value=course)
    monkeypatch.setattr(run, "get_shifu_dto", course_loader)
    outline = SimpleNamespace(shifu_bid="resolved-course", __json__=dict)
    monkeypatch.setattr(run, "get_outline_item_dto", lambda *_: outline)
    struct_loader = Mock(return_value=object())
    monkeypatch.setattr(run, "get_shifu_struct", struct_loader)
    commit, discard, remove = Mock(), Mock(), Mock()
    monkeypatch.setattr(run, "_commit_pending_step", commit)
    monkeypatch.setattr(run, "_discard_session_connection", discard)
    monkeypatch.setattr(run, "_remove_db_session_safely", remove)
    session = Mock()
    monkeypatch.setattr(run, "db", SimpleNamespace(session=session))
    return SimpleNamespace(
        app=Flask(__name__),
        context=context,
        factory=factory,
        course_loader=course_loader,
        struct_loader=struct_loader,
        commit=commit,
        discard=discard,
        remove=remove,
        session=session,
    )


def _execute(execution: object, **kwargs: object) -> object:
    return run.run_script_inner(
        execution.app,
        user_bid="learner",
        shifu_bid="requested-course",
        outline_bid=kwargs.pop("outline_bid", "outline"),
        **kwargs,
    )


@pytest.mark.parametrize("outline", ["", "outline"])
def test_runtime_course_is_resolved_before_constructing_context(
    execution: object, outline: str
) -> None:
    preview_mode = True
    assert (
        list(
            _execute(
                execution,
                outline_bid=outline,
                user_input="answer",
                preview_mode=preview_mode,
            )
        )
        == []
    )
    execution.course_loader.assert_called_once_with(
        execution.app,
        "resolved-course" if outline else "requested-course",
        preview_mode,
    )
    execution.struct_loader.assert_called_once_with(
        execution.app, "resolved-course", preview_mode
    )
    assert execution.factory.call_args.kwargs["is_paid"] is True
    execution.context.set_input.assert_called_once_with("answer", None)
    execution.context._finalize_langfuse_trace.assert_called_once()
    execution.commit.assert_called_once()
    execution.remove.assert_called_once()


def test_missing_course_structure_fails_before_context_creation(
    execution: object,
) -> None:
    execution.struct_loader.return_value = None
    with pytest.raises(AppError) as error:
        list(_execute(execution))
    assert error.value.code == ERROR_CODE["server.shifu.shifuNotFound"]
    execution.factory.assert_not_called()
    execution.commit.assert_not_called()
    execution.session.rollback.assert_called_once()
    execution.remove.assert_called_once()


@pytest.mark.parametrize("reload", [False, True])
def test_preexisting_cancellation_discards_connection_without_running_or_committing(
    execution: object, reload: bool
) -> None:
    stop = threading.Event()
    stop.set()
    execution.context.has_next.return_value = True
    assert (
        list(
            _execute(
                execution,
                stop_event=stop,
                reload_generated_block_bid="old-block" if reload else None,
            )
        )
        == []
    )
    execution.context.run.assert_not_called()
    execution.context.reload.assert_not_called()
    execution.commit.assert_not_called()
    execution.discard.assert_called_once_with(
        source="run_script_inner stop_event cancel"
    )
    execution.remove.assert_called_once()


def test_reload_keeps_element_identity_and_commits_before_starting_next_step(
    execution: object,
) -> None:
    event = RunMarkdownFlowDTO(
        outline_bid="outline",
        generated_block_bid="new-block",
        type=GeneratedType.CONTENT,
        content="Replacement content",
    )
    execution.context.reload.return_value = iter([event])
    stream = _execute(
        execution, reload_generated_block_bid="old-block", reload_element_bid="element"
    )
    assert next(stream) is event
    execution.commit.assert_not_called()
    assert list(stream) == []
    execution.context.reload.assert_called_once_with(
        execution.app, "old-block", reload_element_bid="element"
    )
    assert execution.commit.call_count == 2
    execution.remove.assert_called_once()
