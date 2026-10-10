"""Keep follow-up context anchored to the visible classroom conversation."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.follow_up_context import (
    build_follow_up_conversation_context,
    load_follow_up_history,
)
from flaskr.service.learn.learn_dtos import ElementPayloadDTO
from flaskr.service.learn.listen_element_payloads import _serialize_payload
from flaskr.service.learn.models import LearnGeneratedBlock, LearnGeneratedElement
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
)

if TYPE_CHECKING:
    from flask import Flask


def _seed_classroom(*, sidecars: bool = True) -> LearnGeneratedElement:
    scope = uuid.uuid4().hex
    fields = {
        "progress_record_bid": scope,
        "user_bid": f"user-{scope}",
        "shifu_bid": f"course-{scope}",
        "outline_item_bid": f"lesson-{scope}",
    }

    def block(
        content: str, block_type: int, **overrides: object
    ) -> LearnGeneratedBlock:
        row = LearnGeneratedBlock(
            **(fields | overrides),
            generated_block_bid=uuid.uuid4().hex,
            type=block_type,
            generated_content=content,
            status=1,
        )
        db.session.add(row)
        db.session.flush()
        return row

    with unit_of_work():
        block("Earlier explanation", BLOCK_TYPE_MDCONTENT_VALUE)
        block("My actual answer", BLOCK_TYPE_MDINTERACTION_VALUE)
        for field in fields:
            block(f"Foreign {field}", BLOCK_TYPE_MDCONTENT_VALUE, **{field: "other"})
        block("Deleted explanation", BLOCK_TYPE_MDCONTENT_VALUE, deleted=1)
        retired = block("Retired explanation", BLOCK_TYPE_MDCONTENT_VALUE)
        retired.status = 0
        block("Unrelated question", BLOCK_TYPE_MDASK_VALUE)
        block("Unrelated follow-up", BLOCK_TYPE_MDANSWER_VALUE)
        anchor_block = block(
            "Anchor plus later text in the same turn", BLOCK_TYPE_MDCONTENT_VALUE
        )
        anchor_block.generation_prompt = "PRIVATE MODEL PROMPT"
        anchor_block.block_content_conf = "PRIVATE SCRIPT CONFIG"
        anchor = LearnGeneratedElement(
            **fields,
            element_bid=uuid.uuid4().hex,
            generated_block_bid=anchor_block.generated_block_bid,
            event_type="element",
            element_type="text",
            content_text="Selected anchor",
            status=1,
            is_final=1,
        )
        db.session.add(anchor)
        if sidecars:
            for index, (kind, text) in enumerate(
                [("ask", "Earlier question"), ("answer", "Earlier reply")], 1
            ):
                db.session.add(
                    LearnGeneratedElement(
                        **fields,
                        element_bid=uuid.uuid4().hex,
                        event_type="element",
                        element_type=kind,
                        content_text=text,
                        sequence_number=index,
                        payload=_serialize_payload(
                            ElementPayloadDTO(anchor_element_bid=anchor.element_bid)
                        ),
                        status=1,
                    )
                )
        block("Future lesson text", BLOCK_TYPE_MDCONTENT_VALUE)
        block("Future learner answer", BLOCK_TYPE_MDINTERACTION_VALUE)
    return anchor


@pytest.mark.parametrize("sidecars", [False, True])
def test_anchor_includes_prior_teaching_and_real_answers_only(
    app: Flask, sidecars: bool
) -> None:
    """Completed classroom blocks precede the exact selected text and its own sidecar."""
    with app.app_context():
        anchor = _seed_classroom(sidecars=sidecars)
        before = (
            LearnGeneratedBlock.query.count(),
            LearnGeneratedElement.query.count(),
        )
        history = load_follow_up_history(
            progress_record_bid=anchor.progress_record_bid,
            anchor_element_bid=anchor.element_bid,
            max_history_messages=10,
        )
        expected = [
            {"role": "assistant", "content": "Earlier explanation"},
            {"role": "user", "content": "My actual answer"},
            {"role": "assistant", "content": "Selected anchor"},
        ]
        if sidecars:
            expected.extend(
                [
                    {"role": "user", "content": "Earlier question"},
                    {"role": "assistant", "content": "Earlier reply"},
                ]
            )
        assert history == expected
        assert (
            LearnGeneratedBlock.query.count(),
            LearnGeneratedElement.query.count(),
        ) == before


@pytest.mark.parametrize("limit", [-1, 0, 1, 2, 3, 4])
def test_anchor_budget_prioritizes_recent_sidecar_then_classroom(
    app: Flask, limit: int
) -> None:
    """The anchor is always retained while older classroom turns share the existing limit."""
    with app.app_context():
        anchor = _seed_classroom()
        history = load_follow_up_history(
            progress_record_bid=anchor.progress_record_bid,
            anchor_element_bid=anchor.element_bid,
            max_history_messages=limit,
        )
        extras = max(0, limit)
        expected = []
        if extras >= 4:
            expected.append({"role": "assistant", "content": "Earlier explanation"})
        if extras >= 3:
            expected.append({"role": "user", "content": "My actual answer"})
        expected.append({"role": "assistant", "content": "Selected anchor"})
        if extras >= 2:
            expected.append({"role": "user", "content": "Earlier question"})
        if extras >= 1:
            expected.append({"role": "assistant", "content": "Earlier reply"})
        assert history == expected
        assert len(history) <= extras + 1


def test_anchor_cannot_load_another_progress_history(app: Flask) -> None:
    """An element outside the requested learning attempt provides no conversation."""
    with app.app_context():
        anchor = _seed_classroom()
        assert (
            load_follow_up_history(
                progress_record_bid="different-progress",
                anchor_element_bid=anchor.element_bid,
                max_history_messages=10,
            )
            == []
        )


@pytest.mark.parametrize("change", ["delete", "retire", "unlink", "blank"])
def test_missing_active_anchor_block_keeps_only_selected_text_and_sidecar(
    app: Flask, change: str
) -> None:
    """Partial or legacy data must never fall back to the latest unrelated lesson rows."""
    with app.app_context():
        anchor = _seed_classroom()
        with unit_of_work():
            row = LearnGeneratedBlock.query.filter_by(
                generated_block_bid=anchor.generated_block_bid
            ).one()
            if change == "delete":
                row.deleted = 1
            elif change == "retire":
                row.status = 0
            else:
                anchor.generated_block_bid = (
                    "" if change == "blank" else "missing-block"
                )
        assert load_follow_up_history(
            progress_record_bid=anchor.progress_record_bid,
            anchor_element_bid=anchor.element_bid,
            max_history_messages=10,
        ) == [
            {"role": "assistant", "content": "Selected anchor"},
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier reply"},
        ]


@pytest.mark.parametrize("voice", [False, True])
def test_shared_prompts_use_visible_classroom_history_for_both_transports(
    app: Flask, voice: bool
) -> None:
    """LLM and external providers receive the same scoped classroom conversation."""
    with app.app_context():
        anchor = _seed_classroom()
        result = build_follow_up_conversation_context(
            app,
            user_info=SimpleNamespace(user_id=anchor.user_bid),
            shifu_bid=anchor.shifu_bid,
            outline_item_bid=anchor.outline_item_bid,
            progress_record_bid=anchor.progress_record_bid,
            follow_up_info=SimpleNamespace(ask_prompt="{shifu_system_message}"),
            course_system_prompt=None if voice else "Course instructions",
            fallback_system_prompt="Voice instructions" if voice else None,
            use_learner_language=False,
            runtime_language="en-US",
            runtime_profiles={},
            anchor_element_bid=anchor.element_bid,
        )
        expected = [
            {"role": "assistant", "content": "Earlier explanation"},
            {"role": "user", "content": "My actual answer"},
            {"role": "assistant", "content": "Selected anchor"},
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier reply"},
        ]
        assert result.llm_messages[1:] == result.provider_messages[1:] == expected
        assert (
            "Voice instructions" if voice else "Course instructions"
        ) in result.system_instruction


@pytest.mark.parametrize("preview_mode", [False, True])
@pytest.mark.parametrize("learning_mode", ["read", "listen"])
def test_live_entry_keeps_preceding_classroom_and_its_voice_boundary(
    app: Flask,
    monkeypatch: pytest.MonkeyPatch,
    preview_mode: bool,
    learning_mode: str,
) -> None:
    """The actual Live conversation entry uses scoped history without course instructions."""
    from flaskr.service.learn import follow_up_context as context
    from flaskr.service.learn import live_follow_up_routes as routes
    from flaskr.service.learn.live_follow_up_session_store import (
        LiveFollowUpSessionBinding,
    )
    from flaskr.service.learn.memory import MemorySnapshot

    monkeypatch.setattr(
        context, "load_memory", lambda *_args, **_kwargs: MemorySnapshot(variables={})
    )
    with app.app_context():
        anchor = _seed_classroom()
        monkeypatch.setattr(
            routes,
            "load_user_aggregate",
            lambda _bid: SimpleNamespace(user_id=anchor.user_bid),
        )
        binding = LiveFollowUpSessionBinding(
            session_bid=uuid.uuid4().hex,
            user_bid=anchor.user_bid,
            shifu_bid=anchor.shifu_bid,
            outline_bid=anchor.outline_item_bid,
            anchor_element_bid=anchor.element_bid,
            progress_record_bid=anchor.progress_record_bid,
            preview_mode=preview_mode,
            origin="https://learn.example.com",
            model=routes.GEMINI_LIVE_MODEL_ID,
            voice_name="Kore",
            language="en-US",
            learning_mode=learning_mode,
            expires_at_epoch=900,
        )
        instruction, turns = routes._build_conversation(
            app, binding=binding, follow_up_info=SimpleNamespace(ask_prompt="")
        )
        assert [(turn.role, turn.text) for turn in turns] == [
            ("assistant", "Earlier explanation"),
            ("user", "My actual answer"),
            ("assistant", "Selected anchor"),
            ("user", "Earlier question"),
            ("assistant", "Earlier reply"),
        ]
        assert routes.load_prompt_template("live_follow_up").strip() in instruction
        assert "PRIVATE MODEL PROMPT" not in instruction


@pytest.mark.parametrize("late_snapshot", [False, True])
def test_recent_follow_up_window_keeps_question_answer_turn_order(
    app: Flask,
    late_snapshot: bool,
) -> None:
    """Run-local counters must not group all questions before all answers."""
    with app.app_context():
        anchor = _seed_classroom(sidecars=False)
        fields = {
            key: getattr(anchor, key)
            for key in (
                "progress_record_bid",
                "user_bid",
                "shifu_bid",
                "outline_item_bid",
            )
        }
        first_ask = ""
        first_answer = None
        with unit_of_work():
            for turn in range(7):
                ask_bid = uuid.uuid4().hex
                if turn == 0:
                    first_ask = ask_bid
                for kind, text, sequence in [
                    ("ask", f"Exact learner request {turn}", 61),
                    ("answer", f"Assistant suggestion {turn}", 62),
                ]:
                    row = LearnGeneratedElement(
                        **fields,
                        element_bid=ask_bid if kind == "ask" else uuid.uuid4().hex,
                        run_session_bid=f"run-{turn}",
                        event_type="element",
                        element_type=kind,
                        content_text=text,
                        sequence_number=sequence,
                        run_event_seq=sequence,
                        payload=_serialize_payload(
                            ElementPayloadDTO(
                                anchor_element_bid=anchor.element_bid,
                                ask_element_bid=ask_bid if kind == "answer" else None,
                            )
                        ),
                        status=1,
                    )
                    db.session.add(row)
                    db.session.flush()
                    if turn == 0 and kind == "answer":
                        first_answer = row
            if late_snapshot:
                assert first_answer is not None
                first_answer.status = 0
                db.session.add(
                    LearnGeneratedElement(
                        **fields,
                        element_bid=first_answer.element_bid,
                        run_session_bid="old-run-late-patch",
                        event_type="element",
                        element_type="answer",
                        content_text="Updated old assistant suggestion",
                        sequence_number=999,
                        run_event_seq=999,
                        payload=_serialize_payload(
                            ElementPayloadDTO(
                                anchor_element_bid=anchor.element_bid,
                                ask_element_bid=first_ask,
                            )
                        ),
                        status=1,
                    )
                )
        before = LearnGeneratedElement.query.count()
        history = load_follow_up_history(
            progress_record_bid=anchor.progress_record_bid,
            anchor_element_bid=anchor.element_bid,
            max_history_messages=10,
        )
        expected = [{"role": "assistant", "content": "Selected anchor"}]
        for turn in range(2, 7):
            expected += [
                {"role": "user", "content": f"Exact learner request {turn}"},
                {"role": "assistant", "content": f"Assistant suggestion {turn}"},
            ]
        assert history == expected
        assert LearnGeneratedElement.query.count() == before
