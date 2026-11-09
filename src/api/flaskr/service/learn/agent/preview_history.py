"""Read and promote owned history from legacy independent draft previews."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, require_transaction_owner, unit_of_work
from flaskr.service.learn.agent.interaction_history import structured_user_input
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.agent.session_store import (
    PREVIEW_PRESENTATION_KEY,
    StoredSessionUnusable,
    load_agent_session,
    preview_presentation,
    preview_presentation_from_document,
)
from flaskr.service.learn.elements.history import (
    _attach_follow_up_history_to_anchor_payload,
    _build_final_elements_from_rows,
    _merge_follow_up_elements_after_anchor,
)
from flaskr.service.learn.learn_dtos import (
    ElementPayloadDTO,
    ElementType,
    GeneratedType,
    LearnElementRecordDTO,
)
from flaskr.service.learn.lesson_content_updates import (
    lesson_content_state_from_session,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.learn.progress_ordering import progress_record_order
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_MDASK_VALUE,
)
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.util.datetime import to_utc_iso
from flaskr.util.uuid import generate_id

if TYPE_CHECKING:
    from flask import Flask
    from flaskr.api.markdownflow import Session
    from flaskr.service.learn.agent.lesson_source import ResolvedLessonSource


def begin_preview_run(
    app: Flask, *, user_bid: str, shifu_bid: str, outline_bid: str, run_bid: str
) -> str:
    """Reserve a generation before teaching; record only its exact adapter run IDs.

    Old drafts have no trustworthy presentation ownership. Restart those once rather than
    joining unscoped historical rows or resuming a question whose teaching cannot be restored.
    The reserved row also gives a concurrent reset something to retire on the first turn.
    """
    require_transaction_owner("begin_preview_run", app)
    key = active_key_for(user_bid, outline_bid, preview_mode=True)
    with app_context_scope(app), unit_of_work():
        row = (
            LearnAgentSession.query.filter_by(active_key=key).with_for_update().first()
        )
        if row is not None and row.shifu_bid != shifu_bid:
            message = "Preview session course does not match its lesson"
            raise ValueError(message)
        presentation = preview_presentation(row)
        if presentation and row.schema_version:
            try:
                load_agent_session(app, user_bid, outline_bid, preview_mode=True)
            except StoredSessionUnusable:
                presentation = {}
        if row is not None and not presentation:
            row.deleted, row.active_key = 1, None
            db.session.flush()
            row = None
        if row is None:
            row = LearnAgentSession(
                agent_session_bid=uuid.uuid4().hex,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                active_key=key,
                session_data="{}",
            )
            db.session.add(row)
            presentation = {"version": 1, "runs": [], "questions": {}, "answers": {}}
        if run_bid not in presentation["runs"]:
            presentation["runs"].append(run_bid)
        data = json.loads(row.session_data)
        data[PREVIEW_PRESENTATION_KEY] = presentation
        row.session_data = json.dumps(data, ensure_ascii=False)
        db.session.flush()
        return row.agent_session_bid


def stage_preview_turn(
    *,
    generation: str,
    session: Session,
    generated_block_bid: str,
    turn_record: str,
    question_ids: list[str] | None = None,
) -> None:
    """Bind rendered questions and accepted inputs inside the session save transaction."""
    row = LearnAgentSession.query.filter_by(
        agent_session_bid=generation, deleted=0
    ).one()
    data = json.loads(row.session_data)
    presentation = data[PREVIEW_PRESENTATION_KEY]
    if question_ids:
        # Each emitted control owns one question, even when several share a turn block.
        presentation["questions"][generated_block_bid] = question_ids
    record = json.loads(turn_record).get("agent_turn", {}) if turn_record else {}
    pending = record.get("checkpoint", {}).get("pending", [])
    values = record.get("values", [])
    answered_question_id = None
    if pending and values:
        call_id = pending[0]["tool_call_id"]
        still_pending = {item.tool_call_id for item in session.pending}
        if call_id not in still_pending or call_id in session.answers:
            # Use the learner history encoding so commas inside a value survive replay.
            presentation["answers"][call_id] = structured_user_input(
                pending[0].get("spec"), values
            ) or ",".join(values)
            answered_question_id = call_id
    if record.get("version") == 1 and isinstance(record.get("checkpoint"), dict):
        presentation.setdefault("turns", []).append(
            {
                "block_bid": generated_block_bid,
                "record": record,
                "answered_question_id": answered_question_id,
            }
        )
    row.session_data = json.dumps(data, ensure_ascii=False)


def _owned_legacy_follow_up_rows(
    *, user_bid: str, shifu_bid: str, outline_item_bid: str, anchor_bids: set[str]
) -> list[LearnGeneratedElement]:
    if not anchor_bids:
        return []
    rows = (
        LearnGeneratedElement.query.filter_by(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_item_bid,
            deleted=0,
            status=1,
        )
        .filter(LearnGeneratedElement.element_type.in_(["ask", "answer"]))
        .order_by(LearnGeneratedElement.id)
        .all()
    )
    owned_rows = []
    for row in rows:
        try:
            payload = json.loads(row.payload or "{}")
        except (TypeError, ValueError):
            continue
        anchor = (
            payload.get("anchor_element_bid") if isinstance(payload, dict) else None
        )
        if isinstance(anchor, str) and anchor in anchor_bids:
            owned_rows.append(row)
    return owned_rows


def _stage_owned_legacy_follow_ups(
    progress: LearnProgressRecord, anchor_bids: set[str]
) -> None:
    scope = {
        "user_bid": progress.user_bid,
        "shifu_bid": progress.shifu_bid,
        "outline_item_bid": progress.outline_item_bid,
    }
    rows = _owned_legacy_follow_up_rows(**scope, anchor_bids=anchor_bids)
    if not rows:
        return
    placeholders = db.select(LearnProgressRecord.progress_record_bid).filter_by(
        **scope, deleted=0, status=LEARN_STATUS_NOT_STARTED
    )
    blocks = (
        LearnGeneratedBlock.query.filter_by(**scope, deleted=0, status=1)
        .filter(
            LearnGeneratedBlock.progress_record_bid.in_(placeholders),
            LearnGeneratedBlock.progress_record_bid.in_(
                {row.progress_record_bid for row in rows}
            ),
            LearnGeneratedBlock.type.in_(
                [BLOCK_TYPE_MDASK_VALUE, BLOCK_TYPE_MDANSWER_VALUE]
            ),
        )
        .order_by(LearnGeneratedBlock.created_at, LearnGeneratedBlock.id)
    )
    answers = {}
    questions = {}
    previous_by_progress = {}
    for block in blocks:
        if block.type == BLOCK_TYPE_MDANSWER_VALUE:
            key = (block.generated_block_bid, block.progress_record_bid)
            answers[key] = block
            previous = previous_by_progress.get(block.progress_record_bid)
            if previous is not None and previous.type == BLOCK_TYPE_MDASK_VALUE:
                questions[key] = previous
        previous_by_progress[block.progress_record_bid] = block
    for row in rows:
        key = (row.generated_block_bid, row.progress_record_bid)
        answer = answers.get(key)
        if answer is None:
            continue
        answer.progress_record_bid = progress.progress_record_bid
        row.progress_record_bid = progress.progress_record_bid
        # The old adapter wrote both visible elements against the answer block.
        # Reparent the adjacent question block only when its text corroborates it.
        question = questions.get(key)
        if (
            question is not None
            and row.element_type == ElementType.ASK.value
            and row.content_text == question.generated_content
        ):
            question.progress_record_bid = progress.progress_record_bid


def get_preview_record(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    include_non_navigable: bool = False,
) -> LearnElementRecordDTO:
    """Restore only the active draft's adapter snapshots, in request/event order."""
    from flaskr.service.learn.learn_funcs import get_current_lesson_outline

    with app_context_scope(app):
        row = LearnAgentSession.query.filter_by(
            active_key=active_key_for(user_bid, outline_bid, preview_mode=True),
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            deleted=0,
        ).first()
        try:
            document = json.loads(row.session_data) if row else {}
        except (TypeError, ValueError):
            document = {}
        presentation = preview_presentation_from_document(document)
        current_outline = get_current_lesson_outline(
            shifu_bid=shifu_bid, outline_bid=outline_bid, preview_mode=True
        )
        current = (
            DraftOutlineItem.query.with_entities(DraftOutlineItem.id)
            .filter_by(
                id=current_outline.id,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                deleted=0,
                hidden=0,
            )
            .first()
            if current_outline is not None
            else None
        )
        content_state = lesson_content_state_from_session(
            row=row,
            current_revision=current_outline.content_revision if current else None,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=True,
        )
        elements, events = [], [] if include_non_navigable else None
        if presentation:
            rows = LearnGeneratedElement.query.filter(
                LearnGeneratedElement.user_bid == user_bid,
                LearnGeneratedElement.shifu_bid == shifu_bid,
                LearnGeneratedElement.outline_item_bid == outline_bid,
                LearnGeneratedElement.run_session_bid.in_(presentation["runs"]),
                LearnGeneratedElement.deleted == 0,
                LearnGeneratedElement.status == 1,
            ).all()
            by_run: dict[str, list] = {}
            for item in rows:
                by_run.setdefault(item.run_session_bid, []).append(item)
            seen_questions = set()
            for run_bid in presentation["runs"]:
                current, current_events = _build_final_elements_from_rows(
                    by_run.get(run_bid, []),
                    interaction_user_input_by_block_bid={},
                    include_non_navigable=include_non_navigable,
                )
                question_offsets: dict[str, int] = {}
                for element in current:
                    if element.element_type == ElementType.INTERACTION:
                        block_bid = element.generated_block_bid
                        ids = presentation["questions"].get(block_bid, [])
                        ids = [ids] if isinstance(ids, str) else ids
                        offset = question_offsets.get(block_bid, 0)
                        question_offsets[block_bid] = offset + 1
                        call_id = ids[offset] if offset < len(ids) else None
                        if call_id and call_id in seen_questions:
                            continue
                        if call_id:
                            seen_questions.add(call_id)
                            answer = presentation["answers"].get(call_id)
                            if answer is not None:
                                element.payload = element.payload or ElementPayloadDTO()
                                element.payload.user_input = answer
                    elements.append(element)
                if events is not None:
                    events.extend(current_events or [])
            # ASK runs have an independent semaphore and do not advance the lesson session.
            # Their exact active-generation anchor, rather than their run, owns presentation.
            owned_rows = _owned_legacy_follow_up_rows(
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                anchor_bids={element.element_bid for element in elements},
            )
            by_follow_up_run: dict[str, list] = {}
            for item in owned_rows:
                by_follow_up_run.setdefault(item.run_session_bid, []).append(item)
            for follow_up_run in by_follow_up_run.values():
                current, current_events = _build_final_elements_from_rows(
                    follow_up_run,
                    interaction_user_input_by_block_bid={},
                    include_non_navigable=include_non_navigable,
                )
                elements.extend(current)
                if events is not None:
                    events.extend(current_events or [])
            elements = _merge_follow_up_elements_after_anchor(
                _attach_follow_up_history_to_anchor_payload(elements)
            )
        return LearnElementRecordDTO(
            elements=elements,
            events=events,
            last_progress_updated_at=to_utc_iso(row.created_at) if row else None,
            has_content_update_for_current_user=content_state.has_content_update,
        )


def _legacy_teaching(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    for_update: bool = False,
) -> tuple[LearnAgentSession, Session, dict] | None:
    query = LearnAgentSession.query.filter_by(
        active_key=active_key_for(user_bid, outline_bid, preview_mode=True),
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        deleted=0,
    )
    if for_update:
        query = query.populate_existing().with_for_update()
    row = query.first()
    presentation = preview_presentation(row)
    if row is None or not presentation.get("turns"):
        return None
    try:
        session = load_agent_session(app, user_bid, outline_bid, preview_mode=True)
    except StoredSessionUnusable:
        return None
    if session is None:
        return None
    return row, session, presentation


def legacy_preview_can_resume(
    app: Flask, *, user_bid: str, shifu_bid: str, outline_bid: str
) -> bool:
    """Allow continuation only for a legacy draft whose script still matches."""
    from flaskr.service.learn.learn_funcs import get_current_lesson_outline

    legacy = _legacy_teaching(
        app, user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
    )
    if legacy is None:
        return False
    row, session, _ = legacy
    selected = get_current_lesson_outline(
        shifu_bid=shifu_bid, outline_bid=outline_bid, preview_mode=True
    )
    if selected is None or (
        row.content_revision and row.content_revision != selected.content_revision
    ):
        return False
    outline = DraftOutlineItem.query.filter_by(
        id=selected.id,
        shifu_bid=shifu_bid,
        outline_item_bid=outline_bid,
        deleted=0,
        hidden=0,
    ).first()
    return outline is not None and (outline.content or "") == session.script.script


def promote_legacy_preview_attempt(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    source: ResolvedLessonSource,
    preview_mode: bool,
) -> bool:
    """Attach an owned legacy transcript to the shared attempt without merging sessions."""
    from flaskr.service.learn.agent.lesson_record import (
        apply_outline_progression,
        stage_turn_block,
    )
    from flaskr.service.learn.agent.session_store import bind_lesson_attempt_source
    from flaskr.service.learn.learn_funcs import resolve_outline_progression

    if not source.source.preview_mode:
        return False
    scope = {
        "user_bid": user_bid,
        "shifu_bid": shifu_bid,
        "outline_item_bid": outline_bid,
    }
    with app_context_scope(app), unit_of_work():
        progress = (
            LearnProgressRecord.query.filter_by(**scope, deleted=0)
            .filter(LearnProgressRecord.status != LEARN_STATUS_RESET)
            .order_by(*progress_record_order())
            .populate_existing()
            .with_for_update()
            .first()
        )
        canonical_key = active_key_for(user_bid, outline_bid)
        if (
            LearnAgentSession.query.filter_by(
                **scope, active_key=canonical_key, deleted=0
            )
            .with_for_update()
            .first()
            is not None
        ):
            return False
        legacy = _legacy_teaching(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            for_update=True,
        )
        if legacy is None or (
            progress is not None and progress.status != LEARN_STATUS_NOT_STARTED
        ):
            return False
        row, session, presentation = legacy
        if (source.outline.content or "") != session.script.script or (
            row.content_revision
            and row.content_revision != source.source.content_revision
        ):
            return False
        turns = presentation["turns"]
        block_bids = [turn["block_bid"] for turn in turns]
        if len(set(block_bids)) != len(block_bids):
            return False
        if (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.generated_block_bid.in_(block_bids)
            ).first()
            is not None
        ):
            return False
        snapshots = (
            LearnGeneratedElement.query.filter_by(**scope, deleted=0, status=1)
            .filter(
                LearnGeneratedElement.run_session_bid.in_(presentation["runs"]),
                LearnGeneratedElement.generated_block_bid.in_(block_bids),
            )
            .order_by(LearnGeneratedElement.id.asc())
            .all()
        )
        by_block: dict[str, list[LearnGeneratedElement]] = {}
        for snapshot in snapshots:
            by_block.setdefault(snapshot.generated_block_bid, []).append(snapshot)
        questions_by_block: dict[str, list[str]] = {}
        for bid in block_bids:
            question_ids = presentation["questions"].get(bid, [])
            if isinstance(question_ids, str):
                question_ids = [question_ids]
            if not isinstance(question_ids, list):
                return False
            final_rows = [item for item in by_block.get(bid, []) if item.is_final]
            # Even a silent successful turn writes a boundary. A checkpoint can
            # land before the adapter saves its presentation and boundary.
            if not any(
                item.event_type
                in ("element", GeneratedType.BREAK.value, GeneratedType.DONE.value)
                for item in final_rows
            ):
                return False
            if len(question_ids) > sum(
                item.event_type == "element"
                and item.element_type == ElementType.INTERACTION.value
                for item in final_rows
            ):
                return False
            questions_by_block[bid] = question_ids

        # A placeholder can also contain unrelated follow-ups. The recovered
        # attempt owns only the teaching and follow-ups proven below.
        progress = LearnProgressRecord(
            **scope,
            progress_record_bid=generate_id(app),
            status=LEARN_STATUS_COMPLETED
            if session.finished
            else LEARN_STATUS_IN_PROGRESS,
        )
        db.session.add(progress)
        _stage_owned_legacy_follow_ups(
            progress,
            {
                snapshot.target_element_bid or snapshot.element_bid
                for snapshot in snapshots
                if snapshot.event_type == "element" and snapshot.element_bid
            },
        )
        for turn in turns:
            bid = turn["block_bid"]
            block_rows = by_block.get(bid, [])
            block = stage_turn_block(
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                progress_record_bid=progress.progress_record_bid,
                generated_block_bid=bid,
                position=0,
                content="\n".join(
                    snapshot.content_text
                    for snapshot in block_rows
                    if snapshot.event_type == "element"
                    and snapshot.element_type != ElementType.INTERACTION.value
                    and snapshot.content_text
                ),
            )
            record = {
                **turn["record"],
                "question_ids": questions_by_block[bid],
                "answered_question_id": turn.get("answered_question_id"),
            }
            block.block_content_conf = json.dumps({"agent_turn": record})
            for snapshot in block_rows:
                snapshot.progress_record_bid = progress.progress_record_bid
        row.active_key = canonical_key
        bind_lesson_attempt_source(row, source.source)
        if session.finished:
            updates = resolve_outline_progression(
                app,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                preview_mode=preview_mode,
            )
            if updates:
                apply_outline_progression(
                    app,
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_bid=outline_bid,
                    progress_record_bid=progress.progress_record_bid,
                    updates=updates,
                )
        return True
