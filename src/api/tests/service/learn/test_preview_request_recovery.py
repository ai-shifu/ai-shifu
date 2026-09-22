"""Restore request language and preserve explicit preview history on failures."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.learn import context_v2 as runtime
from flaskr.service.learn.learn_dtos import PlaygroundPreviewRequest


@pytest.fixture
def preview_run(monkeypatch: pytest.MonkeyPatch) -> object:
    app = Flask("preview-request-recovery")
    context = runtime.RunScriptPreviewContextV2(app)
    cache_values = {}
    cache = SimpleNamespace(
        get=cache_values.get,
        setex=lambda key, _ttl, value: cache_values.__setitem__(key, value),
        delete=lambda key: cache_values.pop(key, None),
    )
    monkeypatch.setattr(runtime, "cache_provider", cache)
    monkeypatch.setattr(
        context,
        "_get_outline_record",
        Mock(
            return_value=SimpleNamespace(
                content="?[Continue]",
                title="Lesson",
                outline_item_bid="lesson",
                llm_system_prompt="",
            )
        ),
    )
    monkeypatch.setattr(
        context,
        "_get_shifu_record",
        Mock(
            return_value=SimpleNamespace(llm_system_prompt="", use_learner_language=0)
        ),
    )
    monkeypatch.setattr(
        context, "_load_outline_hierarchy_records", Mock(return_value=[])
    )
    monkeypatch.setattr(context, "_resolve_llm_settings", Mock(return_value=("1", 0.2)))
    monkeypatch.setattr(
        context, "_resolve_preview_variables", Mock(return_value={"language": "fr-FR"})
    )
    monkeypatch.setattr(runtime, "get_langfuse_client", Mock(return_value=None))
    monkeypatch.setattr(
        runtime, "create_trace_with_root_span", Mock(return_value=(None, None))
    )
    finalized = Mock()
    monkeypatch.setattr(runtime, "finalize_langfuse_trace", finalized)
    return SimpleNamespace(
        app=app, context=context, cache=cache_values, finalized=finalized
    )


@pytest.mark.parametrize("outcome", ["complete", "failure", "disconnect"])
def test_preview_language_is_restored_and_explicit_history_survives_all_outcomes(
    preview_run: object,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    seen = []

    def process(_self: object, **kwargs: object) -> object:
        seen.append((runtime.get_current_language(), kwargs))
        if outcome == "failure":
            message = "model unavailable"
            raise RuntimeError(message)
        return SimpleNamespace(content="?[Continuer]", metadata={}, variables={})

    monkeypatch.setattr(runtime.MdflowContextV2, "process", process)
    original_context = [
        {"role": "user", "content": "Earlier prompt"},
        {"role": "assistant", "content": "Earlier answer"},
    ]
    request = PlaygroundPreviewRequest(block_index=0, context=original_context)
    with preview_run.app.app_context():
        runtime.set_language("en-US")
        stream = preview_run.context.stream_preview(
            preview_request=request,
            shifu_bid="course",
            outline_bid="lesson",
            user_bid="teacher",
            session_id="preview",
        )
        if outcome == "failure":
            with pytest.raises(RuntimeError, match="model unavailable"):
                list(stream)
        elif outcome == "disconnect":
            assert next(stream).type == "element"
            stream.close()
        else:
            result = list(stream)
            assert result[-1].type == "done"
        assert runtime.get_current_language() == "en-US"
    assert seen[0][0] == "fr-FR"
    assert seen[0][1]["mode"] == runtime.ProcessMode.COMPLETE
    assert seen[0][1]["user_input"] is None
    assert seen[0][1]["context"] == original_context
    assert len(preview_run.cache) == 1
    entries = json.loads(next(iter(preview_run.cache.values())))["entries"]
    assert entries == [
        {"block_index": -1, "user": "Earlier prompt", "assistant": "Earlier answer"}
    ]
    preview_run.finalized.assert_called_once()


def test_empty_preview_document_fails_before_tracing_or_replacing_history(
    preview_run: object,
) -> None:
    preview_run.context._get_outline_record.return_value.content = ""
    with pytest.raises(ValueError, match="content is empty"):
        list(
            preview_run.context.stream_preview(
                preview_request=PlaygroundPreviewRequest(block_index=0),
                shifu_bid="course",
                outline_bid="lesson",
                user_bid="teacher",
                session_id="preview",
            )
        )
    assert preview_run.cache == {}
    preview_run.finalized.assert_not_called()


@pytest.mark.parametrize("prompt", ["Course guidance", " "])
def test_preview_inherits_course_prompt_when_outline_chain_has_no_prompt(
    preview_run: object,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
) -> None:
    monkeypatch.setattr(
        preview_run.context, "_load_learner_for_course_prompt", Mock(return_value=None)
    )
    result = preview_run.context._resolve_document_prompt(
        PlaygroundPreviewRequest(block_index=0),
        None,
        SimpleNamespace(llm_system_prompt=prompt),
        "course",
        "lesson",
        "teacher",
        {},
    )
    if prompt.strip():
        assert prompt in result
        assert "<composition_contract>" in result
    else:
        assert result is None


@pytest.mark.parametrize("stream_number", [None, "invalid", []])
def test_preview_text_survives_missing_or_malformed_stream_identity(
    preview_run: object,
    stream_number: object,
) -> None:
    event = preview_run.context._make_preview_content_event(
        outline_bid="lesson",
        generated_block_bid="block",
        content="Visible text",
        stream_type="text",
        stream_number=stream_number,
    )
    assert event.content == "Visible text"
    assert event.generated_block_bid == "block"
    assert event.get_mdflow_stream_parts() == []
