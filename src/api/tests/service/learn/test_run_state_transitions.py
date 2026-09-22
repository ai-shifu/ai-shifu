"""Verify lesson-tree transitions and read-side completion state."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.learn import context_v2 as runtime
from flaskr.service.learn.learn_dtos import LearnStatus
from flaskr.service.learn.run import state as state_module
from flaskr.service.order.consts import (
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
)
from flaskr.service.shifu.models import PublishedOutlineItem
from flaskr.service.shifu.shifu_history_manager import HistoryItem


def _node(
    bid: str, row_id: int, *children: object, kind: str = "outline"
) -> HistoryItem:
    return HistoryItem(
        bid=bid,
        id=row_id,
        type=kind,
        children=list(children),
        child_count=len(children),
    )


@pytest.fixture
def tree(monkeypatch: object) -> object:
    first = _node("first", 2)
    hidden = _node("hidden", 3)
    second = _node("second", 5)
    chapter = _node("chapter", 4, second)
    root = _node("course", 1, first, hidden, chapter, kind="shifu")
    context = runtime.RunScriptContextV2.__new__(runtime.RunScriptContextV2)
    context.app = Flask(__name__)
    context._struct = root
    context._preview_mode = False
    context._outline_model = PublishedOutlineItem
    context._user_info = SimpleNamespace(user_id="learner")
    context._current_outline_item = first
    context._current_attend = SimpleNamespace(
        block_position=1, status=LEARN_STATUS_IN_PROGRESS
    )
    context._get_current_outline_block_count = Mock(return_value=1)
    query = Mock()
    query.filter.return_value.all.return_value = [
        ("first", False, "First"),
        ("hidden", True, "Hidden"),
        ("chapter", False, "Chapter"),
        ("second", False, "Second"),
    ]
    monkeypatch.setattr(
        state_module,
        "db",
        SimpleNamespace(session=SimpleNamespace(query=Mock(return_value=query))),
    )
    resolver = state_module.RunStateResolver(context)
    return SimpleNamespace(
        context=context,
        resolver=resolver,
        first=first,
        hidden=hidden,
        second=second,
        chapter=chapter,
    )


def test_completed_lesson_skips_hidden_sibling_and_enters_next_chapters_first_lesson(
    tree: object,
) -> None:
    updates = tree.resolver.get_next_outline_item()
    assert [(item.outline_bid, item.status, item.has_children) for item in updates] == [
        ("first", LearnStatus.COMPLETED, False),
        ("chapter", LearnStatus.IN_PROGRESS, True),
        ("second", LearnStatus.IN_PROGRESS, False),
    ]
    assert tree.resolver.has_next_outline_item(updates) is True
    assert tree.resolver.is_current_outline_completed(updates) is True


def test_finishing_last_lesson_completes_parent_without_starting_another_lesson(
    tree: object,
) -> None:
    tree.context._current_outline_item = tree.second
    updates = tree.resolver.get_next_outline_item()
    assert [(item.outline_bid, item.status) for item in updates] == [
        ("second", LearnStatus.COMPLETED),
        ("chapter", LearnStatus.COMPLETED),
    ]
    assert tree.resolver.has_next_outline_item(updates) is False
    assert tree.resolver.is_current_outline_completed(updates) is True


def test_starting_nested_lesson_marks_its_entire_outline_path_in_progress(
    tree: object,
) -> None:
    tree.context._current_outline_item = tree.second
    tree.context._current_attend.block_position = 0
    tree.context._current_attend.status = LEARN_STATUS_NOT_STARTED
    updates = tree.resolver.get_next_outline_item()
    assert [(item.outline_bid, item.status, item.has_children) for item in updates] == [
        ("chapter", LearnStatus.IN_PROGRESS, True),
        ("second", LearnStatus.IN_PROGRESS, False),
    ]
    assert tree.resolver.is_current_outline_completed(updates) is False


def test_outline_lookup_uses_tree_row_ids_and_returns_none_for_unknown_lessons(
    tree: object,
) -> None:
    assert tree.resolver.get_outline_row_id("second") == 5
    assert tree.resolver.get_outline_row_id("unknown") is None
    assert tree.resolver.get_outline_row_id("") is None
    assert tree.resolver.get_outline_struct("unknown") is None
    tree.context._current_outline_item = None
    assert tree.resolver.is_current_outline_completed([]) is False
    assert tree.resolver.has_next_outline_item([]) is False
    assert tree.resolver.get_current_outline_block_count() == 0


def test_runtime_document_count_is_cached_and_metadata_is_fallback_only(
    tree: object, monkeypatch: object
) -> None:
    loader = Mock(
        side_effect=[
            RuntimeError("document unavailable"),
            SimpleNamespace(mdflow="text"),
        ]
    )
    monkeypatch.setattr(runtime, "get_outline_item_dto_with_mdflow", loader)
    monkeypatch.setattr(
        runtime,
        "MdflowContextV2",
        Mock(return_value=SimpleNamespace(get_all_blocks=lambda: [1, 2, 3])),
    )
    tree.first.child_count = 2
    assert tree.resolver.get_current_outline_block_count() == 2
    assert tree.resolver.get_current_outline_block_count() == 3
    assert tree.resolver.get_current_outline_block_count() == 3
    assert loader.call_count == 2
    tree.context._current_outline_item = tree.chapter
    assert tree.resolver.get_current_outline_block_count() == 1
    assert loader.call_count == 2


@pytest.mark.parametrize("ask", [False, True])
def test_exhausted_lesson_can_still_provide_script_for_follow_up(
    tree: object, monkeypatch: object, ask: bool
) -> None:
    monkeypatch.setattr(
        runtime,
        "get_outline_item_dto_with_mdflow",
        lambda *_a, **_kw: SimpleNamespace(mdflow="Lesson text", outline_bid="first"),
    )
    monkeypatch.setattr(
        runtime,
        "MdflowContextV2",
        Mock(return_value=SimpleNamespace(get_all_blocks=lambda: [object()])),
    )
    attend = SimpleNamespace(outline_item_bid="first", block_position=1)
    result = tree.resolver.get_run_script_info(attend, is_ask=ask)
    if ask:
        assert result.attend is attend
        assert result.mdflow == "Lesson text"
        assert result.block_position == 1
    else:
        assert result is None


@pytest.mark.parametrize(
    ("node", "leaf"),
    [
        (_node("block", 1, kind="block"), False),
        (_node("lesson", 2, _node("block", 3, kind="block")), True),
        (_node("lesson", 4, _node("unknown", 5, kind="unknown")), True),
    ],
)
def test_only_outline_nodes_with_no_outline_children_are_leaf_lessons(
    tree: object, node: HistoryItem, leaf: bool
) -> None:
    assert tree.resolver.is_leaf_outline_item(node) is leaf
