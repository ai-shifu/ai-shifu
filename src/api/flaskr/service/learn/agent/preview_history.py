"""Own classroom draft presentation without creating learner progress records."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from flaskr.dao import db
from flaskr.dao.uow import app_context_scope, require_transaction_owner, unit_of_work
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.agent.session_store import (
    PREVIEW_PRESENTATION_KEY,
    StoredSessionUnusable,
    load_agent_session,
    preview_presentation,
)
from flaskr.service.learn.learn_dtos import (
    ElementPayloadDTO,
    ElementType,
    LearnElementRecordDTO,
    LearnStatus,
    OutlineItemUpdateDTO,
    RunElementSSEMessageDTO,
)
from flaskr.service.learn.listen_element_history import (
    _attach_follow_up_history_to_anchor_payload,
    _build_final_elements_from_rows,
    _merge_follow_up_elements_after_anchor,
)
from flaskr.service.learn.models import LearnGeneratedElement
from flaskr.service.shifu.models import DraftOutlineItem
from flaskr.util.datetime import to_utc_iso

if TYPE_CHECKING:
    from flask import Flask
    from flaskr.service.learn.agent.engine import Session


def has_preview_script(app: Flask, *, shifu_bid: str, outline_bid: str) -> bool:
    """Keep scriptless lessons on their existing 1.0 history and reset path."""
    with app_context_scope(app):
        lesson = (
            DraftOutlineItem.query.filter_by(
                shifu_bid=shifu_bid, outline_item_bid=outline_bid, deleted=0
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        return lesson is not None and bool((lesson.content or "").strip())


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
    if pending and values:
        call_id = pending[0]["tool_call_id"]
        still_pending = {item.tool_call_id for item in session.pending}
        if call_id not in still_pending or call_id in session.answers:
            presentation["answers"][call_id] = ",".join(values)
    row.session_data = json.dumps(data, ensure_ascii=False)


def get_preview_record(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    include_non_navigable: bool = False,
) -> LearnElementRecordDTO:
    """Restore only the active draft's adapter snapshots, in request/event order."""
    with app_context_scope(app):
        row = LearnAgentSession.query.filter_by(
            active_key=active_key_for(user_bid, outline_bid, preview_mode=True),
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            deleted=0,
        ).first()
        presentation = preview_presentation(row)
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
            anchor_bids = {element.element_bid for element in elements}
            follow_up_rows = (
                LearnGeneratedElement.query.filter(
                    LearnGeneratedElement.user_bid == user_bid,
                    LearnGeneratedElement.shifu_bid == shifu_bid,
                    LearnGeneratedElement.outline_item_bid == outline_bid,
                    LearnGeneratedElement.element_type.in_(["ask", "answer"]),
                    LearnGeneratedElement.deleted == 0,
                    LearnGeneratedElement.status == 1,
                )
                .order_by(LearnGeneratedElement.id)
                .all()
            )
            owned_rows = []
            for item in follow_up_rows:
                try:
                    payload = json.loads(item.payload or "{}")
                except (TypeError, ValueError):
                    continue
                if (
                    isinstance(payload, dict)
                    and payload.get("anchor_element_bid") in anchor_bids
                ):
                    owned_rows.append(item)
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
        )


def pending_preview_record(
    app: Flask, *, user_bid: str, shifu_bid: str, outline_bid: str
) -> LearnElementRecordDTO | None:
    """Replay a settled wait after a refresh raced the original stream's final commit."""
    try:
        session = load_agent_session(app, user_bid, outline_bid, preview_mode=True)
    except StoredSessionUnusable:
        return None
    if session is None or not (session.pending or session.finished):
        return None
    record = get_preview_record(
        app, user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
    )
    return record if record.elements else None


def preview_status_event(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    generation: str | None = None,
) -> RunElementSSEMessageDTO | None:
    """Report persisted draft activity to the sidebar without advancing learner progress."""
    with app_context_scope(app):
        query = LearnAgentSession.query.filter_by(
            active_key=active_key_for(user_bid, outline_bid, preview_mode=True),
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            deleted=0,
        )
        if generation is not None:
            query = query.filter_by(agent_session_bid=generation)
        row = query.first()
        lesson = (
            DraftOutlineItem.query.filter_by(
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                deleted=0,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        if row is None or lesson is None:
            return None
        return RunElementSSEMessageDTO(
            type="outline_item_update",
            event_type="outline_item_update",
            content=OutlineItemUpdateDTO(
                outline_bid=outline_bid,
                title=lesson.title or "",
                status=LearnStatus.COMPLETED
                if row.finished
                else LearnStatus.IN_PROGRESS,
                has_children=False,
            ),
        )
