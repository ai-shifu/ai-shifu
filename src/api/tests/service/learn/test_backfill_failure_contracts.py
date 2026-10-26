"""Verify historical element backfill selection and per-record atomicity."""

import runpy
import sys
import uuid
from types import ModuleType, SimpleNamespace

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn import listen_element_mdflow_backfill as backfill
from flaskr.service.learn.const import ROLE_TEACHER
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)


@pytest.fixture
def legacy_formatter(monkeypatch: object) -> object:
    # Older supported MarkdownFlow releases lack format_content; import the
    # compatibility path without replacing the already-loaded service module.
    monkeypatch.setitem(sys.modules, "markdown_flow", ModuleType("markdown_flow"))
    namespace = runpy.run_path(backfill.__file__)
    return namespace["format_content"]


def test_legacy_backfill_formatter_handles_empty_and_unsegmented_content(
    legacy_formatter: object, monkeypatch: object
) -> None:
    monkeypatch.setitem(
        legacy_formatter.__globals__, "build_av_segmentation_contract", lambda _: {}
    )
    assert legacy_formatter(" \n") == []
    result = legacy_formatter("Narration without boundaries")
    assert [(part.content, part.type, part.number) for part in result] == [
        ("Narration without boundaries", "text", 0)
    ]


@pytest.mark.parametrize(
    ("kind", "element_type"),
    [
        ("iframe", "html"),
        ("video", "html"),
        ("sandbox", "html"),
        ("html_table", "html"),
        ("md_table", "tables"),
        ("fence", "code"),
        ("svg", "svg"),
        ("", "text"),
    ],
)
def test_legacy_backfill_formatter_orders_spans_and_normalizes_visual_kinds(
    legacy_formatter: object, monkeypatch: object, kind: str, element_type: str
) -> None:
    contract = {
        "speakable_segments": [
            {"source_span": [6, 10]},
            {"source_span": [0, 3]},
            {"source_span": []},
            {"source_span": [3, 3]},
        ],
        "visual_boundaries": [
            {"kind": kind, "source_span": [3, 6]},
            {"source_span": [1]},
            {"source_span": [5, 4]},
        ],
    }
    monkeypatch.setitem(
        legacy_formatter.__globals__,
        "build_av_segmentation_contract",
        lambda _: contract,
    )
    result = legacy_formatter("abcSVGtail")
    assert [(part.content, part.type, part.number) for part in result] == [
        ("abc", "text", 0),
        ("SVG", element_type, 1),
        ("tail", "text", 2),
    ]


@pytest.fixture
def history(app: object) -> object:
    course = uuid.uuid4().hex
    records = []

    def seed(
        blocks: list[tuple[int, str, str]], *, progress_bid: str | None = None
    ) -> str:
        progress_bid = progress_bid or uuid.uuid4().hex
        with app.app_context(), unit_of_work():
            db.session.add(
                LearnProgressRecord(
                    progress_record_bid=progress_bid,
                    shifu_bid=course,
                    outline_item_bid=course,
                    user_bid=course,
                    status=LEARN_STATUS_IN_PROGRESS,
                )
            )
            for index, (kind, text, interaction) in enumerate(blocks):
                db.session.add(
                    LearnGeneratedBlock(
                        generated_block_bid=uuid.uuid4().hex,
                        progress_record_bid=progress_bid,
                        shifu_bid=course,
                        outline_item_bid=course,
                        user_bid=course,
                        role=ROLE_TEACHER,
                        type=kind,
                        position=index,
                        generated_content=text,
                        block_content_conf=interaction,
                        status=1,
                    )
                )
        records.append(progress_bid)
        return progress_bid

    yield SimpleNamespace(seed=seed, course=course, records=records)
    with app.app_context(), unit_of_work():
        for model in (LearnGeneratedElement, LearnGeneratedBlock, LearnProgressRecord):
            model.query.filter_by(shifu_bid=course).delete()


def test_dry_run_discards_rows_but_reports_the_real_conversion(
    app: object, history: object
) -> None:
    progress = history.seed([(BLOCK_TYPE_MDCONTENT_VALUE, "Readable content.", "")])
    with app.app_context():
        result = backfill.backfill_learn_generated_elements_for_progress(
            app, progress, dry_run=True
        )
        assert result.dry_run is True
        assert result.processed_block_groups == 1
        assert result.inserted_element_rows > 0
        assert (
            LearnGeneratedElement.query.filter_by(shifu_bid=history.course).count() == 0
        )
        persisted = backfill.backfill_learn_generated_elements_for_progress(
            app, progress
        )
        assert persisted.inserted_element_rows == result.inserted_element_rows
        assert (
            LearnGeneratedElement.query.filter_by(
                shifu_bid=history.course, status=1
            ).count()
            == persisted.inserted_element_rows
        )


def test_batch_rolls_back_one_failed_conversion_and_continues_next_progress(
    app: object, history: object, monkeypatch: object
) -> None:
    failed = history.seed(
        [(BLOCK_TYPE_MDCONTENT_VALUE, "Failed progress content.", "")]
    )
    succeeded = history.seed(
        [(BLOCK_TYPE_MDCONTENT_VALUE, "Successful progress content.", "")]
    )
    original = backfill._emit_content_group

    def emit(adapter: object, block: object) -> object:
        messages = original(adapter, block)
        if block.progress_record_bid == failed:
            message = "conversion interrupted after staging rows"
            raise RuntimeError(message)
        return messages

    monkeypatch.setattr(backfill, "_emit_content_group", emit)
    with app.app_context():
        result = backfill.backfill_learn_generated_elements_batch(
            app, progress_record_bids=[failed, succeeded]
        )
        assert result.failed_progress_records == [
            {
                "progress_record_bid": failed,
                "error": "conversion interrupted after staging rows",
            }
        ]
        assert result.processed_progress_records == 1
        assert result.progress_results[0]["progress_record_bid"] == succeeded
        assert (
            LearnGeneratedElement.query.filter_by(progress_record_bid=failed).count()
            == 0
        )
        assert (
            LearnGeneratedElement.query.filter_by(
                progress_record_bid=succeeded, status=1
            ).count()
            == result.inserted_element_rows
        )
        assert result.as_dict()["processed_block_groups"] == 1


def test_explicit_batch_selects_latest_active_duplicate_progress(
    app: object, history: object
) -> None:
    progress = history.seed([])
    history.seed([], progress_bid=progress)
    with app.app_context(), unit_of_work():
        deleted = LearnProgressRecord(
            progress_record_bid=progress,
            shifu_bid=history.course,
            user_bid=history.course,
            outline_item_bid=history.course,
            deleted=1,
        )
        db.session.add(deleted)
    with app.app_context():
        rows = (
            LearnProgressRecord.query.filter_by(progress_record_bid=progress)
            .order_by(LearnProgressRecord.id)
            .all()
        )
        selected = backfill._load_progress_records(
            progress_record_bids=[progress, "missing"], after_id=0, limit=0
        )
        assert [row.id for row in selected] == [rows[1].id]
        assert backfill._load_progress_record(progress).id == rows[1].id


def test_missing_progress_fails_before_creating_an_adapter(
    app: object, monkeypatch: object
) -> None:
    def unexpected_adapter(*_: object, **__: object) -> None:
        pytest.fail("missing progress must fail before conversion")

    monkeypatch.setattr(backfill, "_make_adapter", unexpected_adapter)
    with (
        app.app_context(),
        pytest.raises(ValueError, match="progress record not found"),
    ):
        backfill.backfill_learn_generated_elements_for_progress(app, "absent-progress")


def test_backfill_counts_empty_and_orphan_blocks_without_creating_rows(
    app: object, history: object
) -> None:
    progress = history.seed(
        [
            (BLOCK_TYPE_MDCONTENT_VALUE, " \n", ""),
            (BLOCK_TYPE_MDINTERACTION_VALUE, "", " "),
            (BLOCK_TYPE_MDANSWER_VALUE, "Orphan answer", ""),
            (BLOCK_TYPE_MDASK_VALUE, "Unanswered question", ""),
            (BLOCK_TYPE_MDINTERACTION_VALUE, "", ""),
        ]
    )
    with app.app_context():
        result = backfill.backfill_learn_generated_elements_for_progress(app, progress)
        assert result.skipped_empty_blocks == 3
        assert result.skipped_orphan_follow_ups == 2
        assert result.inserted_element_rows == 0
        assert (
            LearnGeneratedElement.query.filter_by(progress_record_bid=progress).count()
            == 0
        )


def test_duplicate_generated_block_uses_latest_row_and_ignores_missing_identity(
    app: object, history: object
) -> None:
    progress = history.seed(
        [
            (BLOCK_TYPE_MDCONTENT_VALUE, "Obsolete text", ""),
            (BLOCK_TYPE_MDCONTENT_VALUE, "Replacement text", ""),
            (BLOCK_TYPE_MDCONTENT_VALUE, "Missing identity", ""),
        ]
    )
    with app.app_context(), unit_of_work():
        blocks = (
            LearnGeneratedBlock.query.filter_by(progress_record_bid=progress)
            .order_by(LearnGeneratedBlock.id)
            .all()
        )
        blocks[1].generated_block_bid = blocks[0].generated_block_bid
        blocks[2].generated_block_bid = ""
    with app.app_context():
        result = backfill.backfill_learn_generated_elements_for_progress(app, progress)
        rows = LearnGeneratedElement.query.filter_by(
            progress_record_bid=progress, status=1
        ).all()
        assert result.duplicate_blocks_skipped == 1
        assert result.processed_block_groups == 1
        assert "Replacement text" in "".join(row.content_text for row in rows)
        assert "Obsolete text" not in "".join(row.content_text for row in rows)


@pytest.mark.parametrize("overwrite", [False, True])
def test_interaction_backfill_respects_overwrite_policy(
    app: object, history: object, overwrite: bool
) -> None:
    progress = history.seed([(BLOCK_TYPE_MDINTERACTION_VALUE, "", "?[Continue]")])
    with app.app_context():
        first = backfill.backfill_learn_generated_elements_for_progress(app, progress)
        original_ids = [
            row.id
            for row in LearnGeneratedElement.query.filter_by(
                progress_record_bid=progress, status=1
            ).all()
        ]
        second = backfill.backfill_learn_generated_elements_for_progress(
            app, progress, overwrite=overwrite
        )
        active_ids = [
            row.id
            for row in LearnGeneratedElement.query.filter_by(
                progress_record_bid=progress, status=1
            ).all()
        ]
        if overwrite:
            assert second.overwritten_rows == first.inserted_element_rows
            assert not set(original_ids) & set(active_ids)
            assert len(active_ids) == len(original_ids)
        else:
            assert second.skipped_existing_groups == 1
            assert active_ids == original_ids


@pytest.mark.parametrize("kind", ["ask", "answer", "interaction", "unknown"])
def test_non_content_messages_cannot_become_follow_up_anchors(kind: str) -> None:
    message = SimpleNamespace(
        type="element",
        content=SimpleNamespace(
            is_final=True, element_type=kind, element_bid="invalid-anchor"
        ),
    )
    assert backfill._latest_anchor_bid_from_messages([message]) == ""
