"""Verify listen element records and the live listen-element run adapter."""

import json
import types
from datetime import datetime

import pytest
from flaskr.dao import db
from flaskr.service.learn.elements.legacy_record_builder import (
    LegacyGeneratedBlockRecord,
    LegacyLearnRecord,
)
from flaskr.service.learn.learn_dtos import (
    BlockType,
    ElementChangeType,
    ElementDTO,
    ElementType,
    LikeStatus,
    VariableUpdateDTO,
)
from flaskr.service.learn.models import LearnGeneratedElement
from flaskr.service.tts.pipeline import build_av_segmentation_contract

from tests.service.learn.listen_element_helpers import (
    EMPTY_PAYLOAD,
    ListenScope,
    add_rows,
    audio_segment,
    require_app,
    reset_learn_tables,
    streamed_elements,
    subtitle_cues,
)

RUN_ADAPTER = "flaskr.service.learn.elements.run_adapter"


def _forbid_legacy_fallback(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    monkeypatch.setattr(
        f"{RUN_ADAPTER}.get_learn_record",
        lambda *_args, **_kwargs: pytest.fail(reason),
    )


# ---------------------------------------------------------------------------
# get_listen_element_record
# ---------------------------------------------------------------------------


def test_get_listen_element_record_returns_latest_elements_and_events(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-elements", run_session_bid="run-listen-1")
    element_bid = "element-listen-001"
    final_audio = {
        "position": 0,
        "audio_url": "https://example.com/final.mp3",
        "audio_bid": "audio-listen-001",
        "duration_ms": 900,
    }

    def visual_payload(audio: object, image_url: str) -> str:
        return json.dumps(
            {
                "audio": audio,
                "previous_visuals": [{"visual_type": "img", "content": image_url}],
            }
        )

    def event_row(seq: int, event_type: str, **overrides: object) -> object:
        return scope.element(
            run_event_seq=seq,
            event_type=event_type,
            element_index=7,
            is_navigable=0,
            is_final=1,
            **overrides,
        )

    def sandbox_row(seq: int, **overrides: object) -> object:
        return scope.element(
            element_bid=element_bid,
            run_event_seq=seq,
            element_index=7,
            element_type="sandbox",
            element_type_code=102,
            change_type="render",
            **overrides,
        )

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(),
            sandbox_row(
                1,
                content_text="partial",
                payload=visual_payload(None, "https://example.com/partial.png"),
            ),
            sandbox_row(
                2,
                is_final=1,
                content_text="final",
                payload=visual_payload(final_audio, "https://example.com/final.png"),
            ),
            event_row(3, "audio_complete", content_text=json.dumps(final_audio)),
            event_row(
                4,
                "variable_update",
                content_text=json.dumps(
                    {"variable_name": "sys_user_nickname", "variable_value": "Alice"}
                ),
            ),
            event_row(5, "break"),
        )

        result = scope.record(app)

        assert len(result.elements) == 1
        assert result.events is None
        element = result.elements[0]
        assert element.element_bid == element_bid
        assert element.is_final is True
        assert element.content_text == "final"
        assert element.payload is not None
        assert element.payload.audio is not None
        assert element.payload.audio.audio_url == "https://example.com/final.mp3"

        result_with_events = scope.record(app, include_non_navigable=True)

        assert len(result_with_events.elements) == 1
        assert result_with_events.events is not None
        # audio_complete rows are folded into the element, never replayed.
        assert [event.type for event in result_with_events.events] == [
            "element",
            "element",
            "variable_update",
            "break",
        ]
        final_event = result_with_events.events[1]
        assert final_event.run_event_seq == 2
        assert final_event.content.is_final is True
        assert isinstance(result_with_events.events[2].content, VariableUpdateDTO)
        assert result_with_events.events[2].content.variable_name == "sys_user_nickname"


def test_get_listen_element_record_serializes_naive_progress_time_as_utc(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    require_app(app)
    scope = ListenScope("listen-progress-timezone")
    monkeypatch.setitem(app.config, "TZ", "Asia/Shanghai")

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(updated_at=datetime(2026, 6, 30, 11, 57, 3)),
            scope.render(
                element_bid="element-listen-progress-timezone",
                run_event_seq=1,
                element_type="text",
                element_type_code=213,
                is_final=1,
                content_text="timezone check",
            ),
        )
        result = scope.record(app)

    assert result.last_progress_updated_at == "2026-06-30T11:57:03Z"


def test_get_listen_element_record_merges_patch_audio_fields_into_target_snapshot(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-patch-audio")
    element_bid = "element-listen-patch-audio"
    segments = [audio_segment(0, 0, "patch-audio-segment", 180, is_final=False)]

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(),
            scope.render(
                element_bid=element_bid,
                run_event_seq=1,
                element_type="text",
                element_type_code=112,
                sequence_number=1,
                content_text="Narration",
            ),
            scope.render(
                element_bid="element-listen-patch-audio-patch-1",
                run_event_seq=2,
                element_type="text",
                element_type_code=112,
                target_element_bid=element_bid,
                is_new=0,
                sequence_number=2,
                is_speakable=1,
                audio_segments=json.dumps(segments),
                content_text="Narration",
            ),
        )

        result = scope.record(app)

        assert len(result.elements) == 1
        element = result.elements[0]
        assert element.element_bid == element_bid
        assert element.content_text == "Narration"
        assert element.is_speakable is True
        assert element.audio_segments == segments


def test_get_listen_element_record_returns_all_persisted_elements_across_progress_records(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    require_app(app)
    content = ListenScope(
        "listen-all-persisted-elements",
        progress_bid="progress-listen-content",
        generated_block_bid="generated-content-1",
        run_session_bid="run-listen-content",
    )
    interaction = content.replace(
        progress_bid="progress-listen-interaction",
        generated_block_bid="generated-interaction-1",
        run_session_bid="run-listen-interaction",
    )

    with app.app_context():
        reset_learn_tables()
        _forbid_legacy_fallback(
            monkeypatch,
            "persisted element query should not fall back to legacy records",
        )
        add_rows(
            content.progress(),
            interaction.progress(block_position=1),
            content.render(
                element_bid="el_persisted_content",
                run_event_seq=1,
                element_type="text",
                element_type_code=112,
                sequence_number=1,
                is_final=1,
                content_text="Lesson content",
            ),
            interaction.render(
                element_bid="el_only_interaction",
                run_event_seq=1,
                role="ui",
                element_type="interaction",
                element_type_code=105,
                is_marker=1,
                sequence_number=1,
                is_navigable=0,
                is_final=1,
                content_text="Choose one",
            ),
        )

        result = content.record(app)

        assert len(result.elements) == 2
        assert result.elements[0].element_type == ElementType.TEXT
        assert result.elements[0].content_text == "Lesson content"
        assert result.elements[1].element_type == ElementType.INTERACTION
        assert result.elements[1].content_text == "Choose one"
        assert result.elements[1].is_renderable is False


def test_get_listen_element_record_keeps_block_order_when_run_sessions_reset_indexes(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    require_app(app)
    scope = ListenScope("listen-block-order")
    first = scope.with_block("generated-block-first")
    second = scope.with_block("generated-block-second")

    with app.app_context():
        reset_learn_tables()
        monkeypatch.setattr(
            f"{RUN_ADAPTER}.build_legacy_record_for_progress",
            lambda *_args, **_kwargs: LegacyLearnRecord(
                records=[
                    LegacyGeneratedBlockRecord(
                        "generated-block-first",
                        "First block content",
                        LikeStatus.NONE,
                        BlockType.CONTENT,
                        "",
                    ),
                    LegacyGeneratedBlockRecord(
                        "generated-block-second",
                        "Second block content",
                        LikeStatus.NONE,
                        BlockType.CONTENT,
                        "",
                    ),
                ]
            ),
        )
        _forbid_legacy_fallback(
            monkeypatch,
            "persisted element query should not fall back to legacy records",
        )
        add_rows(
            scope.progress(),
            first.render(
                element_bid="element-block-first",
                run_session_bid="run-session-old",
                run_event_seq=5,
                element_index=5,
                element_type="text",
                element_type_code=213,
                sequence_number=5,
                is_final=1,
                content_text="First block content",
            ),
            second.render(
                element_bid="element-block-second",
                run_session_bid="run-session-new",
                run_event_seq=1,
                element_type="text",
                element_type_code=213,
                sequence_number=1,
                is_final=1,
                content_text="Second block content",
            ),
        )

        result = scope.record(app)

        assert [item.generated_block_bid for item in result.elements] == [
            "generated-block-first",
            "generated-block-second",
        ]
        assert [item.content_text for item in result.elements] == [
            "First block content",
            "Second block content",
        ]


def test_get_listen_element_record_ignores_rows_from_inactive_generated_blocks(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-ignore-inactive-blocks")

    def interaction(state: str, seq: int, *, status: int) -> list[object]:
        block = scope.with_block(f"generated-interaction-{state}")
        return [
            block.block(
                block_bid=f"block-interaction-{state}",
                type=1,
                role=2,
                block_content_conf="?[Pick one//pick]",
                status=status,
            ),
            block.render(
                element_bid=f"el-interaction-{state}",
                run_session_bid=f"run-{state}",
                run_event_seq=seq,
                role="ui",
                element_type=ElementType.INTERACTION.value,
                element_type_code=205,
                is_renderable=0,
                is_marker=1,
                sequence_number=seq,
                is_navigable=0,
                is_final=1,
                content_text="?[Pick one//pick]",
            ),
        ]

    def narration(state: str, seq: int, text: str, *, status: int) -> list[object]:
        block = scope.with_block(f"generated-content-{state}")
        return [
            block.block(
                block_bid=f"block-content-{state}",
                role=2,
                generated_content=text,
                position=1,
                block_content_conf=text,
                status=status,
            ),
            block.render(
                element_bid=f"el-content-{state}",
                run_session_bid=f"run-{state}",
                run_event_seq=seq,
                element_index=1,
                element_type=ElementType.TEXT.value,
                element_type_code=213,
                is_renderable=0,
                sequence_number=seq,
                is_speakable=1,
                is_final=1,
                content_text=text,
            ),
        ]

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(block_position=1),
            *interaction("active", 1, status=1),
            *interaction("stale", 2, status=0),
            *narration("active", 3, "Fresh narration", status=1),
            *narration("stale", 4, "Stale narration", status=0),
        )
        result = scope.record(app)

    assert [item.element_bid for item in result.elements] == [
        "el-interaction-active",
        "el-content-active",
    ]
    assert [item.content_text for item in result.elements] == [
        "?[Pick one//pick]",
        "Fresh narration",
    ]


def test_get_listen_element_record_dedupes_older_progress_records_with_same_block_position(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    require_app(app)
    scope = ListenScope("listen-dedupe-progress")
    attempts = {
        label: scope.replace(
            progress_bid=f"progress-listen-{label}",
            generated_block_bid=f"generated-progress-{label}",
            run_session_bid=f"run-progress-{label}",
        )
        for label in ("older", "latest")
    }

    with app.app_context():
        reset_learn_tables()
        _forbid_legacy_fallback(
            monkeypatch,
            "persisted element query should not fall back to legacy records",
        )
        db.session.add_all(
            [attempts["older"].progress(), attempts["latest"].progress()]
        )
        db.session.flush()
        add_rows(
            *(
                attempt.render(
                    element_bid=f"el_progress_{label}",
                    run_event_seq=1,
                    element_type="text",
                    element_type_code=112,
                    sequence_number=1,
                    is_final=1,
                    content_text=text,
                )
                for label, attempt, text in (
                    ("older", attempts["older"], "Older content should be hidden"),
                    ("latest", attempts["latest"], "Latest content should remain"),
                )
            )
        )

        result = scope.record(app)

        assert len(result.elements) == 1
        assert result.elements[0].content_text == "Latest content should remain"
        assert result.elements[0].generated_block_bid == "generated-progress-latest"


def test_get_listen_element_record_includes_persisted_rows_missing_progress_bid(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    require_app(app)
    scope = ListenScope("listen-missing-progress-bid")
    orphan = scope.with_block("generated-orphan-persisted")
    attached = scope.with_block("generated-attached-persisted")

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(),
            orphan.block(
                block_bid="block-orphan-persisted",
                generated_content="legacy should not be needed here",
            ),
            attached.block(
                block_bid="block-attached-persisted",
                generated_content="legacy should not be needed here either",
                position=1,
            ),
            orphan.render(
                element_bid="element-orphan-persisted",
                progress_record_bid="",
                run_event_seq=10,
                element_type="text",
                element_type_code=112,
                sequence_number=1,
                is_final=1,
                content_text="Persisted row with blank progress_record_bid",
            ),
            attached.render(
                element_bid="element-attached-persisted",
                run_event_seq=11,
                element_index=1,
                element_type="text",
                element_type_code=112,
                sequence_number=2,
                is_final=1,
                content_text="Persisted row with linked progress_record_bid",
            ),
        )
        monkeypatch.setattr(
            f"{RUN_ADAPTER}.build_legacy_record_for_progress",
            lambda *_args, **_kwargs: LegacyLearnRecord(records=[]),
        )
        _forbid_legacy_fallback(
            monkeypatch,
            "persisted rows should satisfy the record query without legacy fallback",
        )

        result = scope.record(app)

        assert len(result.elements) == 2
        assert {item.content_text for item in result.elements} == {
            "Persisted row with blank progress_record_bid",
            "Persisted row with linked progress_record_bid",
        }


def test_get_record_api_returns_element_payload_by_default(app: object) -> None:
    require_app(app)
    from flask import request

    scope = ListenScope(
        "record-api-elements",
        generated_block_bid="generated-record-api-elements",
        run_session_bid="run-record-api-1",
    )
    element_bid = "element-record-api-001"

    with app.app_context():
        reset_learn_tables()
        add_rows(
            scope.progress(),
            scope.render(
                element_bid=element_bid,
                run_event_seq=2,
                element_index=3,
                element_type="sandbox",
                element_type_code=102,
                is_final=1,
                content_text="final",
            ),
        )

    with app.test_request_context(
        f"/api/learn/shifu/{scope.shifu_bid}/records/{scope.outline_bid}"
        "?include_non_navigable=true"
    ):
        request.user = types.SimpleNamespace(mobile="", user_id=scope.user_bid)
        response = app.view_functions["get_record_api"](
            scope.shifu_bid, scope.outline_bid
        )

    payload = response.get_json()

    assert payload["code"] == 0
    assert "records" not in payload["data"]
    assert "slides" not in payload["data"]
    assert "interaction" not in payload["data"]
    assert len(payload["data"]["elements"]) == 1
    assert payload["data"]["elements"][0]["element_bid"] == element_bid
    assert payload["data"]["events"][0]["type"] == "element"


# ---------------------------------------------------------------------------
# ListenElementRunAdapter
# ---------------------------------------------------------------------------


def test_listen_element_adapter_retires_fallback_once_visual_element_arrives(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-adapter")
    raw_content = "![img](https://example.com/visual.png)"
    av_contract = build_av_segmentation_contract(raw_content, scope.generated_block_bid)

    with app.app_context():
        reset_learn_tables()
        add_rows(scope.block(generated_content=raw_content))

        adapter = scope.adapter(app)
        streamed = list(
            adapter.process(
                [
                    scope.content(raw_content),
                    scope.audio_complete(
                        audio_url="https://example.com/audio.mp3",
                        audio_bid="audio-listen-adapter",
                        duration_ms=1000,
                        position=0,
                        av_contract=av_contract,
                    ),
                    scope.block_break(),
                ]
            )
        )
        assert [item.type for item in streamed] == [
            "element",
            "element",
            "element",  # retire notification (is_new=false, is_renderable=false)
            "element",  # final visual element with correct type
            "done",
        ]

        audio_patch_evt = streamed[1]
        assert audio_patch_evt.content.element_bid == streamed[0].content.element_bid
        assert audio_patch_evt.content.target_element_bid in ("", None)
        assert audio_patch_evt.content.audio_url == "https://example.com/audio.mp3"
        assert audio_patch_evt.content.is_final is True

        retire_evt = streamed[2]
        assert retire_evt.content.is_new is True
        assert retire_evt.content.is_renderable is False
        assert retire_evt.content.is_final is True
        fallback_element_bid = streamed[0].content.element_bid

        active_rows = LearnGeneratedElement.query.filter(
            LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
            LearnGeneratedElement.generated_block_bid == scope.generated_block_bid,
            LearnGeneratedElement.deleted == 0,
            LearnGeneratedElement.status == 1,
        ).all()
        active_element_bids = {
            row.element_bid for row in active_rows if row.event_type == "element"
        }

        visual_element_bid = next(
            row.element_bid
            for row in active_rows
            if row.event_type == "element" and row.element_bid != fallback_element_bid
        )
        assert visual_element_bid
        assert fallback_element_bid not in active_element_bids


def test_listen_element_adapter_retires_matching_active_rows_by_primary_key(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-retire-active-rows")
    base_element_bid = "element-base"

    with app.app_context():
        reset_learn_tables()
        adapter = scope.adapter(app)

        def text_row(seq: int, **overrides: object) -> object:
            return scope.element(
                progress_record_bid="",
                run_session_bid=adapter.run_session_bid,
                run_event_seq=seq,
                element_type=ElementType.TEXT.value,
                change_type=ElementChangeType.RENDER.value,
                payload=EMPTY_PAYLOAD,
                **overrides,
            )

        add_rows(
            text_row(1, element_bid=base_element_bid, content_text="base"),
            text_row(
                2,
                element_bid="legacy-patch",
                target_element_bid=base_element_bid,
                content_text="legacy patch",
            ),
            text_row(
                3, element_bid="other-element", element_index=1, content_text="other"
            ),
        )

        adapter._persist_element(
            ElementDTO(
                event_type="element",
                element_bid=base_element_bid,
                generated_block_bid=scope.generated_block_bid,
                element_index=0,
                role="teacher",
                element_type=ElementType.TEXT,
                element_type_code=0,
                change_type=ElementChangeType.RENDER,
                is_renderable=True,
                is_new=False,
                is_marker=False,
                is_navigable=1,
                is_final=False,
                content="updated",
                payload=None,
            )
        )

        persisted_rows = (
            LearnGeneratedElement.query.filter(
                LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
                LearnGeneratedElement.generated_block_bid == scope.generated_block_bid,
                LearnGeneratedElement.deleted == 0,
            )
            .order_by(LearnGeneratedElement.id.asc())
            .all()
        )

    assert len(persisted_rows) == 4

    status_by_identity = {
        (row.element_bid, row.target_element_bid or ""): row.status
        for row in persisted_rows
    }
    assert status_by_identity[(base_element_bid, "")] == 0
    assert status_by_identity[("legacy-patch", base_element_bid)] == 0
    assert status_by_identity[("other-element", "")] == 1
    assert status_by_identity[(base_element_bid, base_element_bid)] == 1

    latest_row = persisted_rows[-1]
    assert latest_row.element_bid == base_element_bid
    assert latest_row.target_element_bid == base_element_bid
    assert latest_row.content_text == "updated"


def test_listen_adapter_finalizes_visuals_and_text_as_independent_elements(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-final-text")
    raw_content = (
        "<svg><text>Chart</text></svg>\n\n"
        "After svg.\n\n"
        "<div>Question card</div>\n\n"
        "After html."
    )
    av_contract = build_av_segmentation_contract(raw_content, scope.generated_block_bid)

    def narration(position: int, duration_ms: int, total_ms: int) -> list[object]:
        return [
            scope.audio_segment(
                position=position,
                segment_index=0,
                audio_data=f"segment-{position}",
                duration_ms=duration_ms,
                is_final=position == 1,
                av_contract=av_contract,
            ),
            scope.audio_complete(
                audio_url=f"https://example.com/audio-{position}.mp3",
                audio_bid=f"audio-final-text-{position}",
                duration_ms=total_ms,
                position=position,
                av_contract=av_contract,
            ),
        ]

    with app.app_context():
        reset_learn_tables()
        add_rows(scope.block(generated_content=raw_content))

        adapter = scope.adapter(app)
        streamed = list(
            adapter.process(
                [
                    scope.content(raw_content),
                    *narration(0, 350, 700),
                    *narration(1, 400, 800),
                    scope.block_break(),
                ]
            )
        )
        final_elements = [
            item for item in streamed_elements(streamed) if item.is_final
        ][-4:]
        svg, after_svg, html, after_html = final_elements
        assert [item.element_type.value for item in final_elements] == [
            "svg",
            "text",
            "html",
            "text",
        ]
        assert [item.is_new for item in final_elements] == [True, True, True, True]
        for visual in (svg, html):
            assert visual.is_marker is True
            assert visual.is_renderable is True
            assert visual.content_text == ""
        for position, (text, element) in enumerate(
            (("After svg.", after_svg), ("After html.", after_html))
        ):
            assert element.target_element_bid in ("", None)
            assert element.is_marker is False
            assert element.is_renderable is False
            assert element.is_speakable is True
            assert element.content_text == text
            assert element.audio_url == f"https://example.com/audio-{position}.mp3"
            assert element.audio_segments == [
                audio_segment(
                    position,
                    0,
                    f"segment-{position}",
                    (350, 400)[position],
                    is_final=True,
                )
            ]
        assert svg.payload is not None
        assert svg.payload.previous_visuals[0].visual_type == "svg"
        assert after_svg.payload is not None
        assert after_svg.payload.previous_visuals == []

        persisted_rows = scope.persisted(
            LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
            order_by=(
                LearnGeneratedElement.element_index.asc(),
                LearnGeneratedElement.run_event_seq.asc(),
            ),
        )
        assert [row.element_type for row in persisted_rows] == [
            ElementType.SVG.value,
            ElementType.TEXT.value,
            ElementType.HTML.value,
            ElementType.TEXT.value,
        ]
        for row in (persisted_rows[0], persisted_rows[2]):
            assert row.is_marker == 1
            assert row.is_renderable == 1
            assert row.content_text == ""
        for position, (text, row) in enumerate(
            (("After svg.", persisted_rows[1]), ("After html.", persisted_rows[3]))
        ):
            assert row.is_marker == 0
            assert row.is_renderable == 0
            assert row.is_speakable == 1
            assert row.content_text == text
            assert row.audio_url == f"https://example.com/audio-{position}.mp3"
            # Persisted rows drop the base64 audio data.
            assert json.loads(row.audio_segments) == [
                audio_segment(position, 0, "", (350, 400)[position], is_final=True)
            ]
        assert (
            json.loads(persisted_rows[0].payload)["previous_visuals"][0]["visual_type"]
            == "svg"
        )
        assert json.loads(persisted_rows[1].payload)["previous_visuals"] == []


def test_listen_adapter_finalizes_fallback_text_with_embedded_audio(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-fallback-audio")

    with app.app_context():
        adapter = scope.adapter(app)
        streamed = list(
            adapter.process(
                [
                    scope.content("Fallback narration."),
                    scope.audio_segment(
                        position=0,
                        segment_index=0,
                        audio_data="fallback-segment",
                        duration_ms=280,
                        is_final=True,
                    ),
                    scope.audio_complete(
                        audio_url="https://example.com/fallback-audio.mp3",
                        audio_bid="audio-fallback-0",
                        duration_ms=280,
                        position=0,
                    ),
                    scope.block_break(),
                ]
            )
        )
        final_elements = [
            item
            for item in streamed_elements(streamed)
            if item.is_final and item.is_new
        ]
        assert len(final_elements) == 1
        assert final_elements[0].content_text == "Fallback narration."

        persisted_rows = scope.persisted(
            LearnGeneratedElement.run_session_bid == adapter.run_session_bid,
            order_by=(
                LearnGeneratedElement.run_event_seq.desc(),
                LearnGeneratedElement.id.desc(),
            ),
        )
        assert persisted_rows
        final_row = persisted_rows[0]
        assert final_row.element_type == ElementType.TEXT.value
        assert final_row.is_renderable == 0
        assert final_row.content_text == "Fallback narration."
        assert final_row.is_speakable == 1
        assert final_row.audio_url == "https://example.com/fallback-audio.mp3"
        assert json.loads(final_row.audio_segments) == [
            audio_segment(0, 0, "", 280, is_final=True)
        ]
        payload = json.loads(final_row.payload)
        assert payload["audio"]["audio_bid"] == "audio-fallback-0"
        assert payload["previous_visuals"] == []


def test_listen_adapter_handles_mdflow_stream_metadata_without_av_contract(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-mdflow-stream")
    image = "![img](https://example.com/visual.png)\n"

    with app.app_context():
        scope.seed_block(generated_content=f"{image}caption line\n")

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content(image, "img", 0),
                    scope.content("caption line\n", "img", 0),
                    *(
                        scope.audio_segment(
                            position=0,
                            segment_index=index,
                            audio_data=f"stream-segment-{index}",
                            duration_ms=duration_ms,
                            is_final=False,
                        )
                        for index, duration_ms in enumerate((240, 260))
                    ),
                    scope.audio_complete(
                        audio_url="https://example.com/stream-audio.mp3",
                        audio_bid="audio-stream-1",
                        duration_ms=900,
                        position=0,
                    ),
                    scope.block_break(),
                ]
            )
        )
        assert [item.type for item in streamed] == [
            "element",
            "element",
            "element",
            "done",
        ]

        first_element, patch_element, final_audio_segment_patch = (
            item.content for item in streamed[:3]
        )
        assert first_element.is_new is True
        assert first_element.element_type == ElementType.IMG
        assert "_" not in first_element.element_bid
        assert patch_element.is_new is True
        assert len(patch_element.element_bid) <= 64
        assert patch_element.element_bid == first_element.element_bid
        assert "_" not in patch_element.element_bid
        assert patch_element.target_element_bid in ("", None)
        assert final_audio_segment_patch.is_new is True
        assert final_audio_segment_patch.element_bid == first_element.element_bid
        assert final_audio_segment_patch.target_element_bid in ("", None)
        assert final_audio_segment_patch.audio_url == ""
        assert final_audio_segment_patch.is_final is True
        assert final_audio_segment_patch.audio_segments == []

        result = scope.record(app)

        assert len(result.elements) == 1
        element = result.elements[0]
        assert element.element_bid == first_element.element_bid
        assert element.element_type == ElementType.IMG
        assert element.is_new is True
        assert element.is_final is True
        assert element.is_marker is True
        assert element.audio_url == ""
        assert element.audio_segments == []
        assert element.content_text.endswith("caption line\n")
        assert element.payload is not None
        assert len(element.payload.previous_visuals) == 1
        assert element.payload.previous_visuals[0].visual_type == "img"
        assert element.payload.previous_visuals[0].content == ""

        result_with_events = scope.record(app, include_non_navigable=True)

        assert result_with_events.events is not None
        replay_event_types = [item.type for item in result_with_events.events]
        assert "audio_segment" not in replay_event_types
        assert replay_event_types.count("element") >= 1
        assert "audio_complete" not in replay_event_types
        assert "break" in replay_event_types
        replay_audio_patches = [
            item.content
            for item in result_with_events.events
            if item.type == "element"
            and item.content.audio_segments
            and not item.content.audio_url
            and not item.content.is_final
        ]
        assert replay_audio_patches == []

        persisted_rows = scope.persisted(order_by=(LearnGeneratedElement.id.asc(),))
        persisted_segments = [
            json.loads(row.audio_segments or "[]")
            for row in persisted_rows
            if row.audio_segments and row.audio_segments != "[]"
        ]
        assert persisted_segments == []


def test_listen_adapter_marks_non_text_after_text_as_new_in_stream(app: object) -> None:
    require_app(app)
    scope = ListenScope("listen-is-new-rule")

    with app.app_context():
        scope.seed_block(generated_content="Intro<div>Card</div>Tail")

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content("Intro", "text", 0),
                    scope.content(" more", "text", 0),
                    scope.content("<div>", "html", 1),
                    scope.content("Card</div>", "html", 1),
                    scope.content("Tail", "text", 2),
                ]
            )
        )
        assert [item.type for item in streamed] == [
            "element",
            "element",
            "done",
            "element",
            "element",
            "done",
            "element",
        ]
        element_events = streamed_elements(streamed)

        assert [item.element_type for item in element_events] == [
            ElementType.TEXT,
            ElementType.TEXT,
            ElementType.HTML,
            ElementType.HTML,
            ElementType.TEXT,
        ]
        assert [item.is_new for item in element_events] == [True] * 5
        assert all(item.target_element_bid in ("", None) for item in element_events[1:])


@pytest.mark.parametrize(
    ("slug", "chunks"),
    [
        pytest.param(
            "listen-html-single-on-break",
            ["<div>", "Card</div>"],
            id="tag_split_across_chunks",
        ),
        pytest.param(
            "listen-html-table-chunks",
            ["<table><tbody><tr><td>North", " middle ", "</td></tr></tbody></table>"],
            id="table_split_mid_cell",
        ),
    ],
)
def test_listen_adapter_keeps_html_stream_as_single_element_on_break(
    app: object, slug: str, chunks: list[str]
) -> None:
    require_app(app)
    scope = ListenScope(slug)

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [
                    *(scope.content(chunk, "html", 0) for chunk in chunks),
                    scope.block_break(),
                ]
            )
        )
        html_events = streamed_elements(streamed, ElementType.HTML)

        # One event per chunk plus the final snapshot on break.
        assert len(html_events) == len(chunks) + 1
        assert all(item.is_new is True for item in html_events)
        assert all(item.target_element_bid in ("", None) for item in html_events)
        assert len({item.element_bid for item in html_events}) == 1

        result = scope.record(app)

        assert len(result.elements) == 1
        assert result.elements[0].element_type == ElementType.HTML
        assert result.elements[0].is_new is True


def test_listen_adapter_preserves_structural_fragment_without_html_target(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-structural-fallback")
    style = "<style>*{box-sizing:border-box}</style>"

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [scope.content(style, "html", 0), scope.block_break()]
            )
        )
        element_events = streamed_elements(streamed)

        assert len(element_events) >= 1
        assert element_events[0].element_type == ElementType.HTML
        assert style in element_events[0].content


def test_listen_adapter_marks_type_switch_as_new_when_stream_number_reused(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-stream-switch")

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content("Before image", "text", 0),
                    scope.content("https://example.com/step.png", "img", 0),
                    scope.content("After image", "text", 0),
                ]
            )
        )
        assert [item.type for item in streamed] == [
            "element",
            "done",
            "element",
            "done",
            "element",
        ]
        element_events = streamed_elements(streamed)

        assert [item.element_type for item in element_events] == [
            ElementType.TEXT,
            ElementType.IMG,
            ElementType.TEXT,
        ]
        assert [item.is_new for item in element_events] == [True, True, True]
        assert [item.target_element_bid for item in element_events] == [None] * 3
        assert len({item.element_bid for item in element_events}) == 3


def test_listen_adapter_marks_reentered_image_slot_as_new_after_text(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("listen-reenter-image-slot")

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content("![img](https://example.com/first.png)\n", "img", 0),
                    scope.content("Between images\n", "text", 1),
                    scope.content("![img](https://example.com/second.png)\n", "img", 0),
                ]
            )
        )
        element_events = streamed_elements(streamed)

        assert [item.element_type for item in element_events] == [
            ElementType.IMG,
            ElementType.TEXT,
            ElementType.IMG,
        ]
        assert [item.is_new for item in element_events] == [True, True, True]
        assert element_events[0].target_element_bid in ("", None)
        assert element_events[2].target_element_bid in ("", None)
        assert element_events[0].element_bid != element_events[2].element_bid


def test_audio_segments_stick_to_first_target_element_without_av_contract(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("audio-target-binding")
    first_segment = audio_segment(0, 0, "bound-segment-0", 180, is_final=False)
    second_segment = audio_segment(0, 1, "bound-segment-1", 190, is_final=False)

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content("<div>Intro visual</div>\n", "html", 0),
                    scope.content("Narration text\n", "text", 1),
                    scope.audio_segment(**first_segment),
                    scope.content("<div>Follow-up visual</div>\n", "html", 2),
                    scope.audio_segment(**second_segment),
                    scope.audio_complete(
                        audio_url="https://example.com/bound-audio.mp3",
                        audio_bid="bound-audio-0",
                        duration_ms=370,
                        position=0,
                    ),
                    scope.block_break(),
                ]
            )
        )
        text_elements = streamed_elements(streamed, ElementType.TEXT)
        html_elements = streamed_elements(streamed, ElementType.HTML)
        assert len(text_elements) >= 3
        assert len(html_elements) == 4

        text_element_bid = text_elements[0].element_bid
        assert text_elements[1].element_bid == text_element_bid
        assert text_elements[1].audio_segments == [first_segment]
        assert text_elements[2].element_bid == text_element_bid
        assert text_elements[2].audio_segments == [second_segment]
        audio_complete_text = next(
            item
            for item in text_elements
            if item.audio_url == "https://example.com/bound-audio.mp3"
            and item.element_bid == text_element_bid
        )
        assert audio_complete_text.element_bid == text_element_bid
        assert audio_complete_text.target_element_bid in ("", None)
        assert audio_complete_text.is_final is True
        assert audio_complete_text.audio_segments == [
            first_segment,
            {**second_segment, "is_final": True},
        ]

        intro_html = next(
            item
            for item in html_elements
            if item.is_new and "Intro visual" in (item.content_text or "")
        )
        follow_up_html = next(
            item
            for item in html_elements
            if item.is_new and "Follow-up visual" in (item.content_text or "")
        )
        assert len({item.element_bid for item in html_elements}) == 2
        assert [item.is_new for item in html_elements] == [True, True, True, True]
        assert intro_html.target_element_bid in ("", None)
        assert follow_up_html.target_element_bid in ("", None)
        assert follow_up_html.element_bid != intro_html.element_bid
        assert "Intro visual" not in (follow_up_html.content_text or "")
        assert follow_up_html.audio_segments == []
        assert follow_up_html.audio_url == ""
        assert follow_up_html.is_speakable is False
        assert any(
            item.is_new
            and item.element_bid == intro_html.element_bid
            and "Intro visual" in (item.content_text or "")
            for item in html_elements
        )
        assert any(
            item.is_new
            and item.element_bid == follow_up_html.element_bid
            and "Follow-up visual" in (item.content_text or "")
            for item in html_elements
        )

        text_rows_with_audio = [
            row
            for row in scope.persisted(
                LearnGeneratedElement.element_type == ElementType.TEXT.value
            )
            if row.audio_segments and row.audio_segments != "[]"
        ]
        assert len(text_rows_with_audio) == 1
        assert (
            text_rows_with_audio[0].audio_url == "https://example.com/bound-audio.mp3"
        )
        assert text_rows_with_audio[0].is_final == 1
        assert json.loads(text_rows_with_audio[0].audio_segments) == [
            audio_segment(0, 0, "", 180, is_final=False),
            audio_segment(0, 1, "", 190, is_final=True),
        ]


def test_late_audio_positions_bind_to_latest_text_without_av_contract(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("latest-audio-target-binding")
    second_segments = [
        audio_segment(1, index, f"second-segment-{index}", duration, is_final=False)
        for index, duration in enumerate((210, 220, 230))
    ]

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content("First narration.\n", "text", 0),
                    scope.audio_segment(
                        **audio_segment(0, 0, "first-segment-0", 180, is_final=False)
                    ),
                    scope.audio_complete(
                        audio_url="https://example.com/first-audio.mp3",
                        audio_bid="first-audio-0",
                        duration_ms=180,
                        position=0,
                    ),
                    scope.content("<div>Visual gap</div>\n", "html", 1),
                    scope.content("Second narration.\n", "text", 2),
                    *(scope.audio_segment(**segment) for segment in second_segments),
                    scope.audio_complete(
                        audio_url="https://example.com/second-audio.mp3",
                        audio_bid="second-audio-1",
                        duration_ms=210,
                        position=1,
                    ),
                    scope.block_break(),
                ]
            )
        )
        assert streamed[-1].type == "done"
        text_events = streamed_elements(streamed, ElementType.TEXT)

        rendered_texts = list({item.element_bid: item for item in text_events})
        assert len(rendered_texts) == 2
        first_text_bid, second_text_bid = rendered_texts
        assert first_text_bid != second_text_bid

        first_audio_complete = next(
            item
            for item in text_events
            if item.audio_url == "https://example.com/first-audio.mp3"
        )
        assert first_audio_complete.element_bid == first_text_bid
        assert first_audio_complete.target_element_bid in ("", None)
        assert first_audio_complete.is_final is True

        second_audio_segments = [
            item
            for item in text_events
            if item.element_bid == second_text_bid
            and item.audio_segments
            and not item.audio_url
            and item.audio_segments[0]["position"] == 1
        ]
        assert [item.audio_segments for item in second_audio_segments] == [
            [segment] for segment in second_segments
        ]

        second_audio_complete = next(
            item
            for item in text_events
            if item.audio_url == "https://example.com/second-audio.mp3"
        )
        assert second_audio_complete.element_bid == second_text_bid
        assert second_audio_complete.target_element_bid in ("", None)
        assert second_audio_complete.is_final is True
        assert second_audio_complete.audio_segments == [
            *second_segments[:2],
            {**second_segments[2], "is_final": True},
        ]

        assert not any(
            item.element_bid == first_text_bid
            and any(segment["position"] == 1 for segment in (item.audio_segments or []))
            for item in text_events
        )

        second_text_rows_with_audio = [
            row
            for row in scope.persisted(
                LearnGeneratedElement.element_type == ElementType.TEXT.value
            )
            if row.element_bid == second_text_bid
            and row.audio_segments
            and row.audio_segments != "[]"
        ]
        assert second_text_rows_with_audio
        assert all(
            json.loads(row.audio_segments)[0]["position"] == 1
            for row in second_text_rows_with_audio
        )
        assert all(
            row.audio_url == "https://example.com/second-audio.mp3"
            for row in second_text_rows_with_audio
        )
        final_second_text_row = next(
            row
            for row in reversed(second_text_rows_with_audio)
            if row.audio_url == "https://example.com/second-audio.mp3"
        )
        assert json.loads(final_second_text_row.audio_segments) == [
            audio_segment(1, 0, "", 210, is_final=False),
            audio_segment(1, 1, "", 220, is_final=False),
            audio_segment(1, 2, "", 230, is_final=True),
        ]


def test_listen_adapter_binds_buffered_audio_to_text_after_html(app: object) -> None:
    require_app(app)
    scope = ListenScope("audio-after-html")
    segment = audio_segment(0, 0, "late-text-segment", 210, is_final=True)

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content("<div>Choice detail</div>\n", "html", 0),
                    scope.audio_segment(**segment),
                    scope.content("Narration after click\n", "text", 1),
                    scope.audio_complete(
                        audio_url="https://example.com/after-click.mp3",
                        audio_bid="after-click-audio-0",
                        duration_ms=210,
                        position=0,
                    ),
                    scope.block_break(),
                ]
            )
        )
        html_elements = streamed_elements(streamed, ElementType.HTML)
        text_elements = streamed_elements(streamed, ElementType.TEXT)
        assert len({item.element_bid for item in html_elements}) == 1
        assert len(text_elements) >= 2

        html_element = next(item for item in html_elements if not item.is_final)
        assert html_element.audio_segments == []
        assert html_element.audio_url == ""
        assert html_element.is_speakable is False
        assert all(item.audio_segments == [] for item in html_elements)
        assert all(item.audio_url == "" for item in html_elements)

        initial_text = next(
            item
            for item in text_elements
            if item.content_text == "Narration after click\n"
        )
        assert initial_text.audio_segments == [segment]
        assert initial_text.audio_url == ""
        assert initial_text.is_new is True

        final_text = next(
            item
            for item in text_elements
            if item.audio_url == "https://example.com/after-click.mp3"
            and item.is_final is True
        )
        assert final_text.element_bid == initial_text.element_bid
        assert final_text.target_element_bid in ("", None)
        assert final_text.is_final is True
        assert final_text.audio_segments == [segment]

        persisted_rows = scope.persisted()
        persisted_html_rows = [
            row for row in persisted_rows if row.element_type == ElementType.HTML.value
        ]
        persisted_text_rows = [
            row for row in persisted_rows if row.element_type == ElementType.TEXT.value
        ]
        assert len(persisted_html_rows) == 1
        assert all(
            not row.audio_segments or row.audio_segments == "[]"
            for row in persisted_html_rows
        )
        assert all(row.audio_url == "" for row in persisted_html_rows)
        assert any(
            json.loads(row.audio_segments)
            == [audio_segment(0, 0, "", 210, is_final=True)]
            for row in persisted_text_rows
            if row.audio_segments and row.audio_segments != "[]"
        )
        assert any(
            row.audio_url == "https://example.com/after-click.mp3" and row.is_final == 1
            for row in persisted_text_rows
        )


def test_audio_stream_number_binding_overrides_position_guessing(app: object) -> None:
    require_app(app)
    scope = ListenScope("audio-stream-number-binding")

    def narration(label: str, position: int, number: int, duration_ms: int) -> list:
        stream = {"stream_element_number": number, "stream_element_type": "text"}
        return [
            scope.audio_segment(
                position=position,
                segment_index=0,
                audio_data=f"{label}-segment-0",
                duration_ms=duration_ms,
                is_final=False,
                **stream,
            ),
            scope.audio_complete(
                audio_url=f"https://example.com/{label}-stream.mp3",
                audio_bid=f"{label}-stream-audio",
                duration_ms=duration_ms,
                position=position,
                **stream,
            ),
        ]

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content("# Intro\n", "title", 0),
                    scope.content("First narration\n", "text", 1),
                    scope.content("## Details\n", "title", 2),
                    scope.content("Second narration\n", "text", 3),
                    # Audio arrives in reverse order; stream numbers decide binding.
                    *narration("second", 0, 3, 210),
                    *narration("first", 1, 1, 180),
                    scope.block_break(),
                ]
            )
        )
        final_texts = [
            item
            for item in streamed_elements(streamed, ElementType.TEXT)
            if item.is_final is True
        ]
        first_text_final, second_text_final = (
            next(item for item in final_texts if item.content_text == text)
            for text in ("First narration\n", "Second narration\n")
        )

        assert first_text_final.audio_url == "https://example.com/first-stream.mp3"
        assert first_text_final.audio_segments == [
            audio_segment(1, 0, "first-segment-0", 180, is_final=True)
        ]
        assert second_text_final.audio_url == "https://example.com/second-stream.mp3"
        assert second_text_final.audio_segments == [
            audio_segment(0, 0, "second-segment-0", 210, is_final=True)
        ]


def test_html_only_stream_does_not_absorb_audio_without_av_contract(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("html-only-audio")

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content("<div>Narration after click</div>\n", "html", 0),
                    scope.audio_segment(
                        **audio_segment(0, 0, "html-only-segment", 210, is_final=False)
                    ),
                    scope.audio_complete(
                        audio_url="https://example.com/html-only.mp3",
                        audio_bid="html-only-audio-0",
                        duration_ms=210,
                        position=0,
                    ),
                    scope.block_break(),
                ]
            )
        )
        html_elements = streamed_elements(streamed, ElementType.HTML)

        assert len(html_elements) == 2
        assert streamed_elements(streamed, ElementType.TEXT) == []
        assert all(item.audio_segments == [] for item in html_elements)
        assert all(item.audio_url == "" for item in html_elements)
        assert all(item.is_speakable is False for item in html_elements)

        persisted_html_rows = [
            row
            for row in scope.persisted()
            if row.element_type == ElementType.HTML.value
        ]
        assert len(persisted_html_rows) == 1
        assert all(
            not row.audio_segments or row.audio_segments == "[]"
            for row in persisted_html_rows
        )
        assert all(row.audio_url == "" for row in persisted_html_rows)


def test_duplicate_audio_segment_events_are_deduplicated_in_run_state(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("dup-audio-segment")
    stream = {"stream_element_number": 1, "stream_element_type": "text"}
    segment = audio_segment(0, 0, "segment-0", 180, is_final=False)

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content("Narration\n", "text", 1),
                    scope.audio_segment(**segment, **stream),
                    scope.audio_segment(**segment, **stream),
                    scope.audio_complete(
                        audio_url="https://example.com/segment-0.mp3",
                        audio_bid="audio-segment-0",
                        duration_ms=180,
                        position=0,
                        **stream,
                    ),
                    scope.block_break(),
                ]
            )
        )
        text_final = next(
            item
            for item in streamed_elements(streamed, ElementType.TEXT)
            if item.is_final is True
        )

        assert text_final.audio_segments == [{**segment, "is_final": True}]

        final_rows = scope.persisted(
            LearnGeneratedElement.element_type == ElementType.TEXT.value,
            LearnGeneratedElement.is_final == 1,
            order_by=(LearnGeneratedElement.run_event_seq.desc(),),
        )

        assert final_rows
        assert json.loads(final_rows[0].audio_segments) == [
            audio_segment(0, 0, "", 180, is_final=True)
        ]


def test_listen_adapter_streams_subtitle_cues_on_audio_segment_patch(
    app: object,
) -> None:
    require_app(app)
    scope = ListenScope("stream-segment-subtitles")
    cues = subtitle_cues(("Narration subtitle stream.", 0, 180))

    with app.app_context():
        scope.seed_block()

        streamed = list(
            scope.adapter(app).process(
                [
                    scope.content("Narration subtitle stream.\n", "text", 1),
                    scope.audio_segment(
                        position=0,
                        stream_element_number=1,
                        stream_element_type="text",
                        segment_index=0,
                        audio_data="segment-0",
                        duration_ms=180,
                        is_final=False,
                        subtitle_cues=cues,
                    ),
                ]
            )
        )
        text_events = streamed_elements(streamed, ElementType.TEXT)

        assert len(text_events) == 2
        segment_patch = text_events[-1]
        assert segment_patch.payload is not None
        assert segment_patch.payload.audio is not None
        assert [cue.text for cue in segment_patch.payload.audio.subtitle_cues] == [
            "Narration subtitle stream."
        ]
        assert segment_patch.payload.audio.subtitle_cues[-1].end_ms == 180
        assert segment_patch.payload.audio.duration_ms == 180
        assert segment_patch.audio_segments == [
            audio_segment(0, 0, "segment-0", 180, is_final=False, subtitle_cues=cues)
        ]
        assert segment_patch.payload.audio.duration_ms == sum(
            int(segment["duration_ms"] or 0) for segment in segment_patch.audio_segments
        )
