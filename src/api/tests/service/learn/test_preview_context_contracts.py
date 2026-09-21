"""Cover preview context validation, prompt inheritance and model selection."""

import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.api.llm import model_selection
from flaskr.service.learn import context_v2 as runtime
from flaskr.service.shifu.models import DraftOutlineItem


@pytest.fixture
def preview() -> runtime.RunScriptPreviewContextV2:
    app = Flask("preview-context-contract")
    app.config.update(DEFAULT_LLM_MODEL="default", DEFAULT_LLM_TEMPERATURE=0.7)
    return runtime.RunScriptPreviewContextV2(app)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ([None, {}, {"role": "user", "content": " "}], None),
        (
            [{"role": "assistant", "content": 4}, {"role": "user", "content": "hi"}],
            [{"role": "assistant", "content": "4"}, {"role": "user", "content": "hi"}],
        ),
        (None, None),
    ],
)
def test_model_context_filters_empty_messages_and_normalizes_text(
    raw: object, expected: object
) -> None:
    assert runtime.MdflowContextV2.normalize_context_messages(raw) == expected


@pytest.mark.parametrize("language", ["en", "en-US", "English", ""])
def test_english_runtime_preserves_translation_context(language: str) -> None:
    context = [{"role": "system", "content": "OUTPUT: 100% English"}]
    assert (
        runtime.MdflowContextV2.filter_context_by_output_language(context, language)
        == context
    )


def test_non_english_runtime_removes_conflicting_english_translation_instructions() -> (
    None
):
    context = [
        {"role": "system", "content": "OUTPUT: 100% English"},
        {"role": "system", "content": "Translate ALL non-English"},
        {"role": "user", "content": "Keep lesson material"},
    ]
    assert (
        runtime.MdflowContextV2.filter_context_by_output_language(context, "zh-CN")
        == context[-1:]
    )
    assert (
        runtime.MdflowContextV2.filter_context_by_output_language(context[:2], "fr-FR")
        is None
    )
    assert (
        runtime.MdflowContextV2.filter_context_by_output_language(None, "zh-CN") is None
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ([None, 0, "answer"], {"answer": ["0", "answer"]}),
        ([None], {}),
        (
            {"missing": None, "empty": [], "answer": [None, False]},
            {"answer": ["False"]},
        ),
    ],
)
def test_input_normalization_retains_false_and_zero_answers(
    raw: object, expected: dict
) -> None:
    assert runtime.MdflowContextV2.normalize_user_input_map(raw, "answer") == expected
    assert runtime.MdflowContextV2.flatten_user_input_map({"a": None, "b": 0}) == "0"


@pytest.fixture
def store(
    preview: runtime.RunScriptPreviewContextV2, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    cache = Mock()
    cache.get.return_value = None
    monkeypatch.setattr(runtime, "cache_provider", cache)
    instance = runtime._PreviewContextStore(
        preview.app, "user", "course", "outline", language="fr-FR"
    )
    return SimpleNamespace(instance=instance, cache=cache)


@pytest.mark.parametrize("raw", [b"{}", "", None, "invalid", b"\xff"])
def test_unreadable_preview_cache_degrades_to_empty_context(
    store: SimpleNamespace, raw: object
) -> None:
    store.cache.get.return_value = raw
    assert store.instance.load() == {}


def test_preview_cache_outage_does_not_interrupt_preview(
    store: SimpleNamespace,
) -> None:
    store.cache.get.side_effect = RuntimeError("offline")
    store.cache.setex.side_effect = RuntimeError("offline")
    store.cache.delete.side_effect = RuntimeError("offline")
    assert store.instance.load() == {}
    store.instance.save({"entries": []})
    store.instance.clear()
    assert store.instance._hash_document("") == ""


@pytest.mark.parametrize("entries", [{}, [None], [{"block_index": "1"}]])
def test_invalid_preview_entries_are_cleared_before_replay(
    store: SimpleNamespace, entries: object
) -> None:
    store.cache.get.return_value = json.dumps(
        {"document_hash": store.instance._hash_document("doc"), "entries": entries}
    )
    assert store.instance.get_context("doc", 3) == []
    store.cache.delete.assert_called_once()


def test_preview_context_replacement_retains_unpaired_turns_without_blank_messages(
    store: SimpleNamespace,
) -> None:
    store.instance.replace_context(
        "doc",
        [
            None,
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "last"},
        ],
    )
    _, ttl, raw = store.cache.setex.call_args.args
    assert ttl == 1800
    assert json.loads(raw)["entries"] == [
        {"block_index": -1, "user": "first", "assistant": None},
        {"block_index": -1, "user": "second", "assistant": "reply"},
        {"block_index": -1, "user": "last", "assistant": None},
    ]


def test_preview_prompt_uses_nearest_nonblank_ancestor_once(
    preview: runtime.RunScriptPreviewContextV2, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = DraftOutlineItem(outline_item_bid="current", llm_system_prompt=" ")
    parent = DraftOutlineItem(
        outline_item_bid="parent", llm_system_prompt=" inherited prompt "
    )
    lookup = Mock(return_value=[None, current, parent])
    monkeypatch.setattr(preview, "_load_outline_hierarchy_records", lookup)
    assert (
        preview._resolve_prompt_from_outline_chain("course", "current", current)
        == "inherited prompt"
    )
    lookup.assert_called_once_with(
        shifu_bid="course", outline_bid="current", prefer_draft=True
    )
    current.llm_system_prompt = " own prompt "
    lookup.reset_mock()
    assert (
        preview._resolve_prompt_from_outline_chain("course", "current", current)
        == "own prompt"
    )
    lookup.assert_not_called()
    assert preview._resolve_prompt_from_outline_chain("course", "", None) is None
    lookup.return_value = [
        None,
        DraftOutlineItem(outline_item_bid="empty", llm_system_prompt=""),
    ]
    assert preview._resolve_prompt_from_outline_chain("course", "unknown", None) is None


def test_preview_hierarchy_falls_back_from_unavailable_draft_to_published_records(
    preview: runtime.RunScriptPreviewContextV2, monkeypatch: pytest.MonkeyPatch
) -> None:
    struct = object()
    loader = Mock(side_effect=[RuntimeError("draft unavailable"), struct])
    monkeypatch.setattr(runtime, "get_shifu_struct", loader)
    monkeypatch.setattr(
        runtime,
        "find_node_with_parents",
        lambda *_a: [
            SimpleNamespace(id=1, type="shifu"),
            SimpleNamespace(id=2, type="outline"),
            SimpleNamespace(id=3, type="outline"),
        ],
    )
    parent, child = SimpleNamespace(id=2), SimpleNamespace(id=3)
    query = Mock()
    query.filter.return_value.all.return_value = [parent, child]
    monkeypatch.setattr(
        runtime,
        "PublishedOutlineItem",
        SimpleNamespace(query=query, id=Mock(), deleted=0),
    )
    assert preview._load_outline_hierarchy_records(
        "course", "child", prefer_draft=True
    ) == [child, parent]
    assert [entry.args for entry in loader.call_args_list] == [
        (preview.app, "course", True),
        (preview.app, "course", False),
    ]


@pytest.mark.parametrize("path", [[], [SimpleNamespace(id=1, type="shifu")]])
def test_preview_hierarchy_without_outline_nodes_returns_empty(
    preview: runtime.RunScriptPreviewContextV2,
    monkeypatch: pytest.MonkeyPatch,
    path: list,
) -> None:
    monkeypatch.setattr(runtime, "get_shifu_struct", lambda *_a: object())
    monkeypatch.setattr(runtime, "find_node_with_parents", lambda *_a: path)
    assert (
        preview._load_outline_hierarchy_records("course", "absent", prefer_draft=False)
        == []
    )


@pytest.mark.parametrize(
    ("saved", "expected_index", "reason"),
    [
        ("2", "2", None),
        ("9", "1", "unconfigured_index"),
        ("legacy-model", "1", "invalid_selection"),
        ("", "1", "missing_selection"),
    ],
)
def test_preview_keeps_saved_selection_and_revision_without_resolving_provider(
    preview: runtime.RunScriptPreviewContextV2,
    monkeypatch: pytest.MonkeyPatch,
    saved: str,
    expected_index: str,
    reason: str | None,
) -> None:
    monkeypatch.setattr(
        model_selection,
        "get_configured_model_slots",
        lambda: [{"index": "2", "model": "provider-model"}],
    )
    resolver = Mock(
        side_effect=AssertionError("Static preview must not route a provider")
    )
    monkeypatch.setattr(model_selection, "resolve_model_slot", resolver)
    course = SimpleNamespace(
        llm=saved,
        llm_temperature=Decimal("0.3"),
        id=17,
        __tablename__="draft_shifu",
    )
    assert preview._resolve_llm_settings(course) == (saved, 0.3)
    assert preview._preview_model_selection_metadata == {
        "model_selection_scope": "course",
        "model_selection_original": saved,
        "model_selection_field": "llm",
        "model_selection_table": "draft_shifu",
        "model_selection_record_id": 17,
        "model_index": expected_index,
        "model_selection_fallback": reason is not None,
        "model_selection_fallback_reason": reason,
    }
    resolver.assert_not_called()


def test_static_preview_without_course_keeps_default_temperature(
    preview: runtime.RunScriptPreviewContextV2,
) -> None:
    assert preview._resolve_llm_settings(None) == ("", 0.7)
    assert (
        preview._preview_model_selection_metadata["model_selection_record_id"] is None
    )
    assert (
        preview._preview_model_selection_metadata["model_selection_fallback_reason"]
        == "missing_selection"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        (Decimal("0.25"), 0.25),
        ("0.5", 0.5),
        ("invalid", None),
        ({}, None),
    ],
)
def test_preview_temperature_normalizes_valid_values_only(
    preview: runtime.RunScriptPreviewContextV2, raw: object, expected: object
) -> None:
    assert preview._decimal_to_float(raw) == expected


def test_formatted_content_uses_element_identity_and_falls_back_when_empty() -> None:
    result = SimpleNamespace(
        content="fallback",
        formatted_elements=[
            {},
            {"content": "First", "type": "text", "number": "2"},
            SimpleNamespace(content="Second", type="html", number="invalid"),
        ],
    )
    assert list(runtime._iter_llm_result_content_parts(result)) == [
        ("First", "text", 2),
        ("Second", "html", None),
    ]
    result.formatted_elements = [{}]
    assert list(runtime._iter_llm_result_content_parts(result)) == [
        ("fallback", "", None)
    ]
    assert list(runtime._iter_llm_result_content_parts(None)) == []
    assert list(runtime._iter_llm_result_content_parts("")) == []
    assert list(runtime._iter_llm_result_content_parts("raw text")) == [
        ("raw text", "", None)
    ]
