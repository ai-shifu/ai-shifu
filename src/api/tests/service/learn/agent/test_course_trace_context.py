"""Keep diagnostic outline traversal bounded and its omitted ancestors explicit."""

from types import SimpleNamespace

import pytest
from flaskr.api import langfuse_markdownflow
from flaskr.service.learn.agent import langfuse_tracing as tracing

from tests import test_langfuse_v4_semantics as sdk_tests

captured_spans = sdk_tests.captured_spans


def _context(
    monkeypatch: pytest.MonkeyPatch, parents: dict[str, object]
) -> tuple[dict, list[str]]:
    queried: list[str] = []

    def latest(_model: type, *, outline_bid: str, shifu_bid: str) -> object:
        assert shifu_bid == "course"
        queried.append(outline_bid)
        return parents.get(outline_bid)

    monkeypatch.setattr(tracing, "_latest_ancestor", latest)
    return (
        tracing._lesson_context(
            object,
            outline=SimpleNamespace(
                id=17,
                title="Lesson",
                outline_item_bid="lesson",
                shifu_bid="course",
                parent_bid="chapter-0",
            ),
            shifu=SimpleNamespace(id=4, title="Course", shifu_bid="course"),
        ),
        queried,
    )


def _parents(depth: int) -> dict[str, object]:
    return {
        f"chapter-{index}": SimpleNamespace(
            title=f"Chapter {index}",
            outline_item_bid=f"chapter-{index}",
            parent_bid=f"chapter-{index + 1}" if index + 1 < depth else "",
        )
        for index in range(depth)
    }


def test_deep_outline_names_indicate_omitted_ancestors_without_unbounded_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, queried = _context(monkeypatch, _parents(20))

    assert queried == [f"chapter-{index}" for index in range(12)]
    assert context["chapter_path_truncated"] is True
    assert context["chapter_path"] == [
        f"Chapter {index}" for index in range(11, -1, -1)
    ]
    name = tracing._lesson_name(
        "learn",
        context["course_title"],
        context["chapter_path"],
        context["lesson_title"],
        truncated=context["chapter_path_truncated"],
    )
    assert name.startswith("learn/Course/.../Chapter 11/")
    assert name.endswith("/Chapter 0/Lesson")


def test_request_root_exposes_partial_chapter_path_in_its_name_and_metadata(
    monkeypatch: pytest.MonkeyPatch, captured_spans: object
) -> None:
    client, exporter, _provider = captured_spans
    monkeypatch.setattr(langfuse_markdownflow, "get_langfuse_client", lambda: client)
    _context(monkeypatch, _parents(20))
    trace = tracing.CourseTrace(
        user_bid="learner",
        shifu_bid="course",
        outline_bid="lesson",
        user_input=None,
        preview_mode=False,
        debug=False,
        listen=False,
        learning_mode="read",
        regenerate=False,
    )
    trace.resolved(
        outline_model=object,
        outline=SimpleNamespace(
            id=17,
            title="Lesson",
            outline_item_bid="lesson",
            shifu_bid="course",
            parent_bid="chapter-0",
        ),
        shifu=SimpleNamespace(id=4, title="Course", shifu_bid="course"),
        content_revision=3,
    )
    with trace:
        pass

    (root,) = exporter.get_finished_spans()
    assert root.name.startswith("learn/Course/.../Chapter 11/")
    assert (
        root.attributes["langfuse.observation.metadata.chapter_path_truncated"] is True
    )


@pytest.mark.parametrize("depth", [1, 12])
def test_complete_bounded_path_has_no_truncation_marker(
    monkeypatch: pytest.MonkeyPatch, depth: int
) -> None:
    context, queried = _context(monkeypatch, _parents(depth))

    assert len(queried) == depth
    assert context["chapter_path_truncated"] is False
    name = tracing._lesson_name(
        "preview",
        context["course_title"],
        context["chapter_path"],
        context["lesson_title"],
        truncated=context["chapter_path_truncated"],
    )
    assert "/.../" not in name


def test_cycle_stops_without_requerying_or_claiming_depth_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parents = _parents(3)
    parents["chapter-2"].parent_bid = "chapter-0"
    context, queried = _context(monkeypatch, parents)

    assert queried == ["chapter-0", "chapter-1", "chapter-2"]
    assert context["chapter_path"] == ["Chapter 2", "Chapter 1", "Chapter 0"]
    assert context["chapter_path_truncated"] is False


def test_missing_parent_stops_without_unbounded_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, queried = _context(monkeypatch, {})

    assert queried == ["chapter-0"]
    assert context["chapter_path"] == []
    assert context["chapter_path_truncated"] is False


def test_long_trace_name_preserves_the_missing_prefix_and_identity_budget() -> None:
    name = tracing._lesson_name(
        "debug",
        "Course title " * 15,
        ["Long chapter title " * 20],
        "Lesson title " * 15,
        truncated=True,
    )

    assert len(name) <= 180
    assert name.startswith("debug/Course")
    assert "/.../" in name
    assert "Lesson" in name
