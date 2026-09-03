"""Verify Gemini Live transcript persistence and shared follow-up context."""

from __future__ import annotations

import json
import types
import uuid
from unittest.mock import patch

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.service.learn import follow_up_context as follow_up_context_module
from flaskr.service.learn.follow_up_context import (
    build_follow_up_conversation_context,
    build_follow_up_element_history,
)
from flaskr.service.learn.learn_dtos import ElementPayloadDTO
from flaskr.service.learn.listen_element_payloads import (
    _deserialize_payload,
    _serialize_payload,
)
from flaskr.service.learn.live_follow_up_persistence import (
    LiveFollowUpPersistenceError,
    LiveTurnPersistenceContext,
    LiveTurnPersistenceInput,
    deterministic_live_turn_bid,
    persist_live_follow_up_turn,
)
from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement
from flaskr.service.learn.utils_v2 import FollowUpInfo
from flaskr.service.metering import BillUsageRecord
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
)


def _persistence_context(*, session_bid: str) -> LiveTurnPersistenceContext:
    return LiveTurnPersistenceContext(
        session_bid=session_bid,
        user_bid="live-user",
        shifu_bid="live-shifu",
        outline_item_bid="live-outline",
        progress_record_bid=f"progress-{session_bid[:8]}",
        anchor_element_bid=f"anchor-{session_bid[:8]}",
        preview_mode=False,
        learning_mode="listen",
        request_id="request-live",
        trace_id="trace-live",
    )


def _insert_anchor(context: LiveTurnPersistenceContext) -> None:
    db.session.add(
        LearnGeneratedElement(
            element_bid=context.anchor_element_bid,
            progress_record_bid=context.progress_record_bid,
            user_bid=context.user_bid,
            generated_block_bid="anchor-block",
            outline_item_bid=context.outline_item_bid,
            shifu_bid=context.shifu_bid,
            run_session_bid="lesson-run",
            run_event_seq=20,
            event_type="element",
            role="teacher",
            element_index=7,
            element_type="text",
            element_type_code=213,
            change_type="render",
            target_element_bid="",
            is_renderable=0,
            is_new=1,
            is_marker=0,
            sequence_number=20,
            is_speakable=0,
            audio_url="",
            audio_segments="[]",
            is_navigable=1,
            is_final=1,
            content_text="Anchor lesson text",
            payload=_serialize_payload(ElementPayloadDTO()),
            deleted=0,
            status=1,
        )
    )
    db.session.commit()


def test_live_turn_persists_interrupted_empty_answer_idempotently(app: Flask) -> None:
    """A terminal turn writes one stable ASK/ANSWER pair and never settles usage."""
    session_bid = str(uuid.uuid4())
    context = _persistence_context(session_bid=session_bid)
    usage = {
        "promptTokenCount": 31,
        "responseTokenCount": 17,
        "totalTokenCount": 48,
        "cachedContentTokenCount": 5,
        "promptTokensDetails": [
            {"modality": "TEXT", "tokenCount": 11},
            {"modality": "AUDIO", "tokenCount": 20},
        ],
        "responseTokensDetails": [
            {"modality": "AUDIO", "tokenCount": 17},
        ],
    }
    turn = LiveTurnPersistenceInput(
        turn_index=3,
        user_transcript="  What did that mean?  ",
        played_answer_transcript="",
        interrupted=True,
        usage_metadata=usage,
        latency_ms=245,
    )

    with app.app_context():
        _insert_anchor(context)
        with patch(
            "flaskr.service.metering.recorder._enqueue_usage_settlement"
        ) as enqueue_settlement:
            first = persist_live_follow_up_turn(app, context, turn)
            second = persist_live_follow_up_turn(app, context, turn)

        assert first == second
        assert first.history_saved is True
        assert first.ask_block_bid == deterministic_live_turn_bid(
            session_bid, 3, "ask-block"
        )
        assert first.answer_element_bid == deterministic_live_turn_bid(
            session_bid, 3, "answer-element"
        )
        assert (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.generated_block_bid.in_(
                    [first.ask_block_bid, first.answer_block_bid]
                )
            ).count()
            == 2
        )
        assert (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.element_bid.in_(
                    [first.ask_element_bid, first.answer_element_bid]
                )
            ).count()
            == 2
        )

        ask_block = LearnGeneratedBlock.query.filter_by(
            generated_block_bid=first.ask_block_bid
        ).one()
        answer_block = LearnGeneratedBlock.query.filter_by(
            generated_block_bid=first.answer_block_bid
        ).one()
        assert ask_block.type == BLOCK_TYPE_MDASK_VALUE
        assert ask_block.generated_content == "What did that mean?"
        assert answer_block.type == BLOCK_TYPE_MDANSWER_VALUE
        assert answer_block.generated_content == ""

        ask_element = LearnGeneratedElement.query.filter_by(
            element_bid=first.ask_element_bid
        ).one()
        answer_element = LearnGeneratedElement.query.filter_by(
            element_bid=first.answer_element_bid
        ).one()
        assert ask_element.element_index == answer_element.element_index == 7
        assert ask_element.is_navigable == answer_element.is_navigable == 0
        assert ask_element.change_type == answer_element.change_type == "render"
        assert ask_element.audio_url == answer_element.audio_url == ""
        assert ask_element.audio_segments == answer_element.audio_segments == "[]"
        assert answer_element.content_text == ""
        assert answer_element.sequence_number > ask_element.sequence_number

        ask_payload = json.loads(ask_element.payload)
        answer_payload = json.loads(answer_element.payload)
        expected_payload = {
            "anchor_element_bid": context.anchor_element_bid,
            "interaction_mode": "live_voice",
            "interrupted": True,
            "live_session_bid": session_bid,
            "live_turn_index": 3,
        }
        for key, value in expected_payload.items():
            assert ask_payload[key] == value
            assert answer_payload[key] == value
        assert "ask_element_bid" not in ask_payload
        assert answer_payload["ask_element_bid"] == first.ask_element_bid

        usage_row = BillUsageRecord.query.filter_by(usage_bid=first.usage_bid).one()
        assert usage_row.billable == 0
        assert usage_row.input == 31
        assert usage_row.input_cache == 5
        assert usage_row.output == 17
        assert usage_row.total == 48
        assert usage_row.generated_block_bid == first.answer_block_bid
        assert usage_row.extra["gemini_usage"] == usage
        assert usage_row.extra["usage_source"] == (
            "gemini_live_follow_up_client_report"
        )
        assert usage_row.extra["usage_attestation"] == "client_reported_untrusted"
        assert usage_row.extra["interaction_mode"] == "live_voice"
        assert usage_row.extra["live_session_bid"] == session_bid
        assert usage_row.extra["live_turn_index"] == 3
        assert "user_transcript" not in usage_row.extra
        assert "played_answer_transcript" not in usage_row.extra
        enqueue_settlement.assert_not_called()


def test_live_turn_saves_the_played_answer_transcript(app: Flask) -> None:
    """Completed history stores the browser-played answer text, not audio."""
    session_bid = str(uuid.uuid4())
    context = _persistence_context(session_bid=session_bid)
    turn = LiveTurnPersistenceInput(
        turn_index=2,
        user_transcript="Can you give an example?",
        played_answer_transcript="Here is the part that actually played.",
        interrupted=False,
        usage_metadata={"totalTokenCount": 12},
    )

    with app.app_context():
        result = persist_live_follow_up_turn(app, context, turn)
        answer_block = LearnGeneratedBlock.query.filter_by(
            generated_block_bid=result.answer_block_bid
        ).one()
        answer_element = LearnGeneratedElement.query.filter_by(
            element_bid=result.answer_element_bid
        ).one()
        assert answer_block.generated_content == turn.played_answer_transcript
        assert answer_element.content_text == turn.played_answer_transcript
        assert answer_element.audio_url == ""
        assert answer_element.audio_segments == "[]"


def test_live_turn_without_final_user_transcript_only_records_usage(app: Flask) -> None:
    """Missing final learner transcription must not fabricate ASK/ANSWER history."""
    session_bid = str(uuid.uuid4())
    context = _persistence_context(session_bid=session_bid)
    turn = LiveTurnPersistenceInput(
        turn_index=1,
        user_transcript="   ",
        played_answer_transcript="Unpaired model speech",
        interrupted=False,
        usage_metadata={
            "promptTokenCount": 9,
            "responseTokenCount": 4,
            "promptTokensDetails": [{"modality": "AUDIO", "tokenCount": 9}],
        },
    )

    with app.app_context():
        result = persist_live_follow_up_turn(app, context, turn)

        assert result.history_saved is False
        assert result.ask_block_bid == ""
        assert result.answer_block_bid == ""
        assert result.ask_element_bid == ""
        assert result.answer_element_bid == ""
        assert (
            LearnGeneratedElement.query.filter_by(run_session_bid=session_bid).count()
            == 0
        )
        assert (
            LearnGeneratedBlock.query.filter_by(
                progress_record_bid=context.progress_record_bid
            ).count()
            == 0
        )

        usage_row = BillUsageRecord.query.filter_by(usage_bid=result.usage_bid).one()
        assert usage_row.billable == 0
        assert usage_row.generated_block_bid == ""
        assert usage_row.total == 13
        assert usage_row.extra["gemini_usage"]["promptTokensDetails"] == [
            {"modality": "AUDIO", "tokenCount": 9}
        ]


def test_live_turn_bounds_and_allowlists_untrusted_usage(app: Flask) -> None:
    """Client reports cannot inject metadata or overflow usage counters."""
    session_bid = str(uuid.uuid4())
    context = _persistence_context(session_bid=session_bid)
    turn = LiveTurnPersistenceInput(
        turn_index=8,
        user_transcript="",
        played_answer_transcript="",
        interrupted=False,
        usage_metadata={
            "promptTokenCount": float("nan"),
            "candidatesTokenCount": 10**100,
            "totalTokenCount": -5,
            "thoughtsTokenCount": True,
            "rawError": "must not persist",
            "candidatesTokensDetails": [
                {"modality": "audio", "tokenCount": 12.9},
                {"modality": "SECRET", "tokenCount": 99},
                {"modality": "TEXT", "tokenCount": float("inf")},
            ],
        },
    )

    with app.app_context():
        result = persist_live_follow_up_turn(app, context, turn)
        usage_row = BillUsageRecord.query.filter_by(usage_bid=result.usage_bid).one()

        assert usage_row.input == 0
        assert usage_row.output == 2_147_483_647
        assert usage_row.total == 2_147_483_647
        assert usage_row.extra["gemini_usage"] == {
            "candidatesTokenCount": 2_147_483_647,
            "totalTokenCount": 0,
            "candidatesTokensDetails": [{"modality": "AUDIO", "tokenCount": 12}],
        }
        assert "rawError" not in usage_row.extra["gemini_usage"]


def test_live_turn_does_not_acknowledge_failed_usage_write(app: Flask) -> None:
    """A best-effort recorder failure remains retryable instead of losing usage."""
    session_bid = str(uuid.uuid4())
    context = _persistence_context(session_bid=session_bid)
    turn = LiveTurnPersistenceInput(
        turn_index=1,
        user_transcript="",
        played_answer_transcript="",
        interrupted=False,
        usage_metadata={"totalTokenCount": 3},
    )

    with (
        app.app_context(),
        patch(
            "flaskr.service.learn.live_follow_up_persistence.record_llm_usage",
            return_value="",
        ),
        pytest.raises(
            LiveFollowUpPersistenceError,
            match="usage persistence failed",
        ),
    ):
        persist_live_follow_up_turn(app, context, turn)


def test_live_turn_retry_after_usage_failure_is_idempotent(app: Flask) -> None:
    """A retry fills client-reported usage without duplicating history."""
    session_bid = str(uuid.uuid4())
    context = _persistence_context(session_bid=session_bid)
    turn = LiveTurnPersistenceInput(
        turn_index=4,
        user_transcript="Please explain that again.",
        played_answer_transcript="Here is another explanation.",
        interrupted=False,
        usage_metadata={"totalTokenCount": 7},
    )
    usage_bid = deterministic_live_turn_bid(session_bid, 4, "usage")

    with app.app_context():
        with (
            patch(
                "flaskr.service.learn.live_follow_up_persistence.record_llm_usage",
                side_effect=["", usage_bid],
            ),
            pytest.raises(LiveFollowUpPersistenceError),
        ):
            persist_live_follow_up_turn(app, context, turn)

        result = persist_live_follow_up_turn(app, context, turn)

        assert result.usage_bid == usage_bid
        assert (
            LearnGeneratedBlock.query.filter_by(
                progress_record_bid=context.progress_record_bid
            ).count()
            == 2
        )
        assert (
            LearnGeneratedElement.query.filter_by(run_session_bid=session_bid).count()
            == 2
        )


def test_shared_element_history_prefers_sidecars_and_bounds_zero() -> None:
    """Canonical sidecars win over embedded history and zero retains only anchor."""
    anchor = types.SimpleNamespace(content_text="Anchor")
    rows = [
        types.SimpleNamespace(
            element_type="ask",
            content_text="legacy container",
            payload=_serialize_payload(
                ElementPayloadDTO(
                    asks=[
                        {"role": "student", "content": "legacy q"},
                        {"role": "teacher", "content": "legacy a"},
                    ]
                )
            ),
        ),
        types.SimpleNamespace(
            element_type="ask",
            content_text="new q",
            payload=_serialize_payload(ElementPayloadDTO()),
        ),
        types.SimpleNamespace(
            element_type="answer",
            content_text="new a",
            payload=_serialize_payload(ElementPayloadDTO()),
        ),
    ]

    assert build_follow_up_element_history(anchor, rows, 10) == [
        {"role": "assistant", "content": "Anchor"},
        {"role": "user", "content": "new q"},
        {"role": "assistant", "content": "new a"},
    ]
    assert build_follow_up_element_history(anchor, rows, 0) == [
        {"role": "assistant", "content": "Anchor"}
    ]


def test_shared_context_composes_profiles_language_prompt_and_history(
    monkeypatch: object,
) -> None:
    """Text and Live transports receive the same composed instruction and history."""
    app = Flask("shared-live-follow-up-context")
    user_info = types.SimpleNamespace(
        user_id="user-id",
        user_bid="user-bid",
        identify="learner@example.com",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        follow_up_context_module,
        "get_user_profiles",
        lambda *_args: {
            "sys_user_nickname": "Alex",
            "sys_user_language": "en-US",
        },
    )

    def fake_build_course_prompt(
        prompt: str,
        *,
        variables: dict[str, object],
        nickname_identifiers: tuple[str, str, str],
    ) -> str:
        captured["prompt"] = prompt
        captured["variables"] = dict(variables)
        captured["nickname_identifiers"] = nickname_identifiers
        return "BUILT COURSE"

    monkeypatch.setattr(
        follow_up_context_module,
        "build_course_prompt",
        fake_build_course_prompt,
    )
    monkeypatch.setattr(
        follow_up_context_module,
        "render_course_prompt_identity_variables",
        lambda prompt, _variables: f"{prompt} RENDERED",
    )
    monkeypatch.setattr(
        follow_up_context_module,
        "replace_variables_in_text",
        lambda prompt, _variables: f"{prompt} REPLACED",
    )
    monkeypatch.setattr(
        follow_up_context_module,
        "get_fmt_prompt",
        lambda *_args, **_kwargs: "FORMATTED COURSE",
    )
    history = [
        {"role": "assistant", "content": "Anchor"},
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
    ]
    monkeypatch.setattr(
        follow_up_context_module,
        "load_follow_up_history",
        lambda **_kwargs: list(history),
    )

    result = build_follow_up_conversation_context(
        app,
        user_info=user_info,
        shifu_bid="shifu",
        outline_item_bid="outline",
        progress_record_bid="progress",
        follow_up_info=FollowUpInfo(
            ask_model="model",
            ask_prompt="FOLLOW-UP\n{shifu_system_message}",
            ask_history_count=0,
            ask_limit_count=0,
            model_args={},
            ask_mode=1,
        ),
        course_system_prompt="COURSE TEMPLATE",
        use_learner_language=True,
        runtime_language="zh-CN",
        runtime_profiles=None,
        anchor_element_bid="anchor",
        max_history_messages=20,
    )

    assert captured["prompt"] == "COURSE TEMPLATE"
    assert captured["variables"] == {
        "sys_user_nickname": "Alex",
        "sys_user_language": "zh-CN",
        "language": "zh-CN",
    }
    assert captured["nickname_identifiers"] == (
        "user-bid",
        "user-id",
        "learner@example.com",
    )
    assert result.output_language == "简体中文"
    assert result.system_instruction == (
        "FOLLOW-UP\nFORMATTED COURSE\n\nIMPORTANT: You MUST respond in 简体中文."
    )
    assert result.llm_messages == [
        {"role": "system", "content": result.system_instruction},
        *history,
    ]
    assert result.provider_messages == [
        {"role": "system", "content": "FORMATTED COURSE"},
        *history,
    ]


def test_live_payload_round_trip_rejects_invalid_metadata_types() -> None:
    """The existing payload serializer retains only bounded Live contract fields."""
    payload = ElementPayloadDTO(
        anchor_element_bid="anchor",
        ask_element_bid="ask",
        interaction_mode="live_voice",
        live_session_bid="session",
        live_turn_index=0,
        interrupted=False,
    )
    restored = _deserialize_payload(_serialize_payload(payload))
    assert restored.interaction_mode == "live_voice"
    assert restored.live_session_bid == "session"
    assert restored.live_turn_index == 0
    assert restored.interrupted is False

    invalid = _deserialize_payload(
        json.dumps(
            {
                "interaction_mode": "audio-ish",
                "live_turn_index": True,
                "interrupted": "yes",
            }
        )
    )
    assert invalid.interaction_mode is None
    assert invalid.live_turn_index is None
    assert invalid.interrupted is None
