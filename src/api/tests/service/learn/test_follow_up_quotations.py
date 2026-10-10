"""Verify exact role-scoped quote evidence without model or database calls."""

import json

import pytest
from flaskr.service.learn.follow_up_quotations import (
    QUOTATION_RESULT_BYTES,
    LearnerQuotationSource,
)


def test_quote_source_excludes_assistant_system_and_current_question() -> None:
    original = "  Please remember “library loans”.\nKeep the spaces.  "
    history = [
        {"role": "system", "content": "Teacher instructions"},
        {"role": "user", "content": original},
        {"role": "assistant", "content": "Try saying: Remember library loans."},
        {"role": "user", "content": "What were my exact words?"},
    ]
    before = [dict(m) for m in history]
    source = LearnerQuotationSource.from_history(history)
    history[1]["content"] = "Changed after capture"
    result = json.loads(source.read())
    assert result["messages"] == [
        {
            "source_index": 0,
            "role": "learner",
            "status": "available",
            "content": original,
        }
    ]
    assert result["coverage"] == "supplied_history_only"
    assert result["next_offset"] is None
    assert before[1]["content"] == source.messages[0]


@pytest.mark.parametrize("offset", [-1, 2])
def test_quote_invalid_offsets_do_not_expose_content(offset: int) -> None:
    assert json.loads(LearnerQuotationSource(("private",)).read(offset)) == {
        "status": "invalid_offset"
    }


def test_empty_window_does_not_claim_the_learner_never_said_something() -> None:
    source = LearnerQuotationSource.from_history(
        [
            {"role": "assistant", "content": "You said: Remember library loans."},
            {"role": "user", "content": "Quote my earlier request."},
        ]
    )
    result = json.loads(source.read())
    assert result == {
        "status": "learner_messages",
        "coverage": "supplied_history_only",
        "messages": [],
        "next_offset": None,
    }
    assert source.page_count() == 1


@pytest.mark.parametrize("extra", [0, 1])
def test_exact_utf8_result_boundary_never_returns_a_shortened_quote(extra: int) -> None:
    overhead = len(LearnerQuotationSource(("",)).read().encode("utf-8"))
    size = QUOTATION_RESULT_BYTES - overhead
    original = "界" * (size // 3) + "x" * (size % 3 + extra)
    raw = LearnerQuotationSource((original,)).read()
    assert len(raw.encode("utf-8")) <= QUOTATION_RESULT_BYTES
    entry = json.loads(raw)["messages"][0]
    if extra:
        assert entry == {"source_index": 0, "role": "learner", "status": "too_large"}
    else:
        assert len(raw.encode("utf-8")) == QUOTATION_RESULT_BYTES
        assert entry["content"] == original


@pytest.mark.parametrize(
    "messages", [tuple(str(i) for i in range(43)), ("a" * 5000,) * 3]
)
def test_quote_pages_preserve_every_complete_source_in_order(
    messages: tuple[str, ...],
) -> None:
    source = LearnerQuotationSource(messages)
    offset, pages, entries = 0, 0, []
    while offset is not None:
        raw = source.read(offset)
        assert len(raw.encode("utf-8")) <= QUOTATION_RESULT_BYTES
        page = json.loads(raw)
        entries.extend(page["messages"])
        assert page["next_offset"] is None or page["next_offset"] > offset
        offset = page["next_offset"]
        pages += 1
    assert [entry["content"] for entry in entries] == list(messages)
    assert [entry["source_index"] for entry in entries] == list(range(len(messages)))
    assert pages == source.page_count()


def test_oversized_quote_does_not_hide_later_available_messages() -> None:
    source = LearnerQuotationSource(("z" * 9000, "Exact later source"))
    result = json.loads(source.read())
    assert result["messages"][0]["status"] == "too_large"
    assert "content" not in result["messages"][0]
    assert result["messages"][1]["content"] == "Exact later source"
    assert result["next_offset"] is None
