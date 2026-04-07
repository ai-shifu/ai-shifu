# ruff: noqa: E402

import json
import sys
import types


def _install_litellm_stub() -> None:
    if "litellm" in sys.modules:
        return

    litellm_stub = types.ModuleType("litellm")
    litellm_stub.get_max_tokens = lambda _model: 4096
    litellm_stub.completion = lambda *args, **kwargs: iter([])
    sys.modules["litellm"] = litellm_stub


def _install_openai_responses_stub() -> None:
    if "openai.types.responses" in sys.modules:
        return

    responses_pkg = types.ModuleType("openai.types.responses")
    responses_pkg.__path__ = []
    response_mod = types.ModuleType("openai.types.responses.response")
    response_create_mod = types.ModuleType(
        "openai.types.responses.response_create_params"
    )
    response_function_mod = types.ModuleType(
        "openai.types.responses.response_function_tool_call"
    )
    response_text_mod = types.ModuleType(
        "openai.types.responses.response_text_config_param"
    )

    for name in [
        "IncompleteDetails",
        "Response",
        "ResponseOutputItem",
        "Tool",
        "ToolChoice",
    ]:
        setattr(response_mod, name, type(name, (), {}))

    for name in [
        "Reasoning",
        "ResponseIncludable",
        "ResponseInputParam",
        "ToolChoice",
        "ToolParam",
        "Text",
    ]:
        setattr(response_create_mod, name, type(name, (), {}))

    response_function_tool_call = type("ResponseFunctionToolCall", (), {})
    response_text_config = type("ResponseTextConfigParam", (), {})
    setattr(
        response_function_mod,
        "ResponseFunctionToolCall",
        response_function_tool_call,
    )
    setattr(
        response_text_mod,
        "ResponseTextConfigParam",
        response_text_config,
    )
    setattr(
        responses_pkg,
        "ResponseFunctionToolCall",
        response_function_tool_call,
    )

    sys.modules["openai.types.responses"] = responses_pkg
    sys.modules["openai.types.responses.response"] = response_mod
    sys.modules["openai.types.responses.response_create_params"] = response_create_mod
    sys.modules["openai.types.responses.response_function_tool_call"] = (
        response_function_mod
    )
    sys.modules["openai.types.responses.response_text_config_param"] = response_text_mod


_install_litellm_stub()
_install_openai_responses_stub()

from flaskr.dao import db
from flaskr.service.learn.const import ROLE_TEACHER
from flaskr.service.learn.listen_element_mdflow_backfill import (
    backfill_learn_generated_elements_batch,
    backfill_learn_generated_elements_for_progress,
)
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


def _clear_learn_tables() -> None:
    LearnGeneratedElement.query.delete()
    LearnGeneratedBlock.query.delete()
    LearnProgressRecord.query.delete()
    db.session.commit()


def _make_progress(
    *,
    progress_record_bid: str,
    shifu_bid: str = "shifu-1",
    outline_item_bid: str = "outline-1",
    user_bid: str = "user-1",
) -> LearnProgressRecord:
    progress = LearnProgressRecord(
        progress_record_bid=progress_record_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_item_bid,
        user_bid=user_bid,
        status=LEARN_STATUS_IN_PROGRESS,
        block_position=0,
    )
    db.session.add(progress)
    return progress


def _make_block(
    *,
    generated_block_bid: str,
    progress_record_bid: str,
    outline_item_bid: str,
    shifu_bid: str,
    user_bid: str,
    block_type: int,
    generated_content: str,
    position: int,
    block_content_conf: str = "",
) -> LearnGeneratedBlock:
    block = LearnGeneratedBlock(
        generated_block_bid=generated_block_bid,
        progress_record_bid=progress_record_bid,
        user_bid=user_bid,
        block_bid=f"block-{generated_block_bid}",
        outline_item_bid=outline_item_bid,
        shifu_bid=shifu_bid,
        type=block_type,
        role=ROLE_TEACHER,
        generated_content=generated_content,
        position=position,
        block_content_conf=block_content_conf,
        status=1,
        deleted=0,
    )
    db.session.add(block)
    return block


def test_mdflow_backfill_persists_content_follow_up_and_interaction(app):
    with app.app_context():
        _clear_learn_tables()
        progress = _make_progress(progress_record_bid="progress-mdflow-1")
        progress_record_bid = progress.progress_record_bid
        raw_content = "Before intro.\n\n<svg><text>Chart</text></svg>\n\nAfter chart."
        content_block = _make_block(
            generated_block_bid="generated-content-1",
            progress_record_bid=progress.progress_record_bid,
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            user_bid=progress.user_bid,
            block_type=BLOCK_TYPE_MDCONTENT_VALUE,
            generated_content=raw_content,
            position=0,
        )
        _make_block(
            generated_block_bid="generated-ask-1",
            progress_record_bid=progress.progress_record_bid,
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            user_bid=progress.user_bid,
            block_type=BLOCK_TYPE_MDASK_VALUE,
            generated_content="Why is this chart important?",
            position=1,
        )
        answer_block = _make_block(
            generated_block_bid="generated-answer-1",
            progress_record_bid=progress.progress_record_bid,
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            user_bid=progress.user_bid,
            block_type=BLOCK_TYPE_MDANSWER_VALUE,
            generated_content="It summarizes the key transition.",
            position=1,
        )
        interaction_block = _make_block(
            generated_block_bid="generated-interaction-1",
            progress_record_bid=progress.progress_record_bid,
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            user_bid=progress.user_bid,
            block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
            generated_content="Bob",
            position=2,
            block_content_conf="?[%{{nickname}} Alice | Bob]",
        )
        content_block_bid = content_block.generated_block_bid
        answer_block_bid = answer_block.generated_block_bid
        interaction_block_bid = interaction_block.generated_block_bid
        db.session.commit()

        result = backfill_learn_generated_elements_for_progress(
            app,
            progress_record_bid,
        )

        rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.progress_record_bid == progress_record_bid,
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            )
            .order_by(
                LearnGeneratedElement.run_event_seq.asc(),
                LearnGeneratedElement.id.asc(),
            )
            .all()
        )

    assert result.processed_block_groups == 3
    assert result.inserted_element_rows == 6
    assert result.skipped_anchorless_follow_ups == 0
    assert result.skipped_orphan_follow_ups == 0

    content_rows = [row for row in rows if row.generated_block_bid == content_block_bid]
    assert [row.element_type for row in content_rows] == ["text", "svg", "text"]
    assert all(row.audio_url == "" for row in content_rows)
    assert all(
        json.loads(row.payload or "{}").get("audio") is None for row in content_rows
    )

    anchor_bid = content_rows[-1].element_bid

    follow_up_rows = [
        row for row in rows if row.generated_block_bid == answer_block_bid
    ]
    assert [row.element_type for row in follow_up_rows] == ["ask", "answer"]
    assert all(row.audio_url == "" for row in follow_up_rows)
    ask_payload = json.loads(follow_up_rows[0].payload or "{}")
    answer_payload = json.loads(follow_up_rows[1].payload or "{}")
    assert ask_payload["anchor_element_bid"] == anchor_bid
    assert answer_payload["anchor_element_bid"] == anchor_bid
    assert answer_payload["ask_element_bid"] == follow_up_rows[0].element_bid

    interaction_rows = [
        row for row in rows if row.generated_block_bid == interaction_block_bid
    ]
    assert len(interaction_rows) == 1
    interaction_payload = json.loads(interaction_rows[0].payload or "{}")
    assert interaction_rows[0].element_type == "interaction"
    assert interaction_rows[0].role == "ui"
    assert interaction_payload["user_input"] == "Bob"


def test_mdflow_backfill_skips_anchorless_follow_up(app):
    with app.app_context():
        _clear_learn_tables()
        progress = _make_progress(progress_record_bid="progress-mdflow-anchorless")
        _make_block(
            generated_block_bid="generated-ask-anchorless",
            progress_record_bid=progress.progress_record_bid,
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            user_bid=progress.user_bid,
            block_type=BLOCK_TYPE_MDASK_VALUE,
            generated_content="Question without anchor",
            position=0,
        )
        _make_block(
            generated_block_bid="generated-answer-anchorless",
            progress_record_bid=progress.progress_record_bid,
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            user_bid=progress.user_bid,
            block_type=BLOCK_TYPE_MDANSWER_VALUE,
            generated_content="Answer without anchor",
            position=0,
        )
        db.session.commit()

        result = backfill_learn_generated_elements_for_progress(
            app,
            progress.progress_record_bid,
        )
        active_count = LearnGeneratedElement.query.filter(
            LearnGeneratedElement.progress_record_bid == progress.progress_record_bid,
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        ).count()

    assert result.processed_block_groups == 0
    assert result.skipped_anchorless_follow_ups == 1
    assert active_count == 0


def test_mdflow_backfill_skips_orphan_follow_up(app):
    with app.app_context():
        _clear_learn_tables()
        progress = _make_progress(progress_record_bid="progress-mdflow-orphan")
        _make_block(
            generated_block_bid="generated-content-orphan",
            progress_record_bid=progress.progress_record_bid,
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            user_bid=progress.user_bid,
            block_type=BLOCK_TYPE_MDCONTENT_VALUE,
            generated_content="Anchor content.",
            position=0,
        )
        _make_block(
            generated_block_bid="generated-ask-orphan",
            progress_record_bid=progress.progress_record_bid,
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            user_bid=progress.user_bid,
            block_type=BLOCK_TYPE_MDASK_VALUE,
            generated_content="Question without answer",
            position=1,
        )
        db.session.commit()

        result = backfill_learn_generated_elements_for_progress(
            app,
            progress.progress_record_bid,
        )
        follow_up_count = LearnGeneratedElement.query.filter(
            LearnGeneratedElement.progress_record_bid == progress.progress_record_bid,
            LearnGeneratedElement.element_type.in_(["ask", "answer"]),
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        ).count()

    assert result.processed_block_groups == 1
    assert result.skipped_orphan_follow_ups == 1
    assert follow_up_count == 0


def test_mdflow_backfill_overwrite_replaces_group_rows(app):
    with app.app_context():
        _clear_learn_tables()
        progress = _make_progress(progress_record_bid="progress-mdflow-overwrite")
        block = _make_block(
            generated_block_bid="generated-content-overwrite",
            progress_record_bid=progress.progress_record_bid,
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            user_bid=progress.user_bid,
            block_type=BLOCK_TYPE_MDCONTENT_VALUE,
            generated_content="Fresh content.",
            position=0,
        )
        db.session.commit()

        db.session.add(
            LearnGeneratedElement(
                element_bid="legacy-element-overwrite",
                progress_record_bid=progress.progress_record_bid,
                user_bid=progress.user_bid,
                generated_block_bid=block.generated_block_bid,
                outline_item_bid=progress.outline_item_bid,
                shifu_bid=progress.shifu_bid,
                run_session_bid="legacy-run",
                run_event_seq=1,
                event_type="element",
                role="teacher",
                element_index=0,
                element_type="text",
                element_type_code=213,
                change_type="render",
                target_element_bid="",
                is_renderable=0,
                is_new=1,
                is_marker=0,
                sequence_number=1,
                is_speakable=0,
                audio_url="",
                audio_segments="[]",
                is_navigable=1,
                is_final=1,
                content_text="Legacy content.",
                payload=json.dumps({"audio": None, "previous_visuals": []}),
                deleted=0,
                status=1,
            )
        )
        db.session.commit()

        skipped = backfill_learn_generated_elements_for_progress(
            app,
            progress.progress_record_bid,
        )
        overwritten = backfill_learn_generated_elements_for_progress(
            app,
            progress.progress_record_bid,
            overwrite=True,
        )

        rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.progress_record_bid
                == progress.progress_record_bid,
                LearnGeneratedElement.deleted == 0,
            )
            .order_by(LearnGeneratedElement.id.asc())
            .all()
        )

    assert skipped.processed_block_groups == 0
    assert skipped.skipped_existing_groups == 1
    assert overwritten.processed_block_groups == 1
    assert overwritten.overwritten_rows == 1
    assert rows[0].status == 0
    assert rows[-1].status == 1
    assert rows[-1].content_text.startswith("Fresh content.")


def test_mdflow_backfill_batch_respects_after_id_and_limit(app):
    with app.app_context():
        _clear_learn_tables()
        progress_1 = _make_progress(progress_record_bid="progress-mdflow-batch-1")
        progress_2 = _make_progress(progress_record_bid="progress-mdflow-batch-2")
        progress_3 = _make_progress(progress_record_bid="progress-mdflow-batch-3")
        db.session.flush()
        progress_1_id = int(progress_1.id)
        progress_2_bid = progress_2.progress_record_bid

        for progress in (progress_1, progress_2, progress_3):
            _make_block(
                generated_block_bid=f"generated-{progress.progress_record_bid}",
                progress_record_bid=progress.progress_record_bid,
                outline_item_bid=progress.outline_item_bid,
                shifu_bid=progress.shifu_bid,
                user_bid=progress.user_bid,
                block_type=BLOCK_TYPE_MDCONTENT_VALUE,
                generated_content=f"Content for {progress.progress_record_bid}",
                position=0,
            )
        db.session.commit()

        batch = backfill_learn_generated_elements_batch(
            app,
            after_id=progress_1_id,
            limit=1,
        )

        active_progress_bids = {
            row.progress_record_bid
            for row in LearnGeneratedElement.query.filter(
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            ).all()
        }

    assert batch.processed_progress_records == 1
    assert batch.failed_progress_records == []
    assert [item["progress_record_bid"] for item in batch.progress_results] == [
        progress_2_bid
    ]
    assert active_progress_bids == {progress_2_bid}
