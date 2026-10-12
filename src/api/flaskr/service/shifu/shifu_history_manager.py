"""Shifu history manager.

This module contains functions for managing shifu history.

Author: yfge
Date: 2025-08-07

tree structure:

format:
{
    "bid": "bid",
    "id": "id",
    "type": "shifu",
    "data": [
        {
            "id": "id",
            "type": "outline",
            "children": [
                {
                    "bid": "bid",
                    "type": "outline",
                    "children": [
                        {
                            "bid": "bid",
                            "type": "block",
                            "children": []
                        }
                    ]
                }
            ]
        }
    ]
}

"""

import queue
import re
from collections.abc import Iterator
from typing import Generic, TypeVar

from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import app_context_scope
from flaskr.service.user.models import UserInfo
from flaskr.util import generate_id
from flaskr.util.datetime import now_utc, to_utc_iso
from pydantic import BaseModel
from sqlalchemy import literal, select, tuple_, union_all

from .models import DraftOutlineItem, LogDraftStruct

T = TypeVar("T", bound="HistoryItem")
OUTLINE_CONTENT_LOOKBACK_LIMIT = 1000
# Buffer at most 400 historical bodies per query; prompt sizes vary by course.
OUTLINE_CONTENT_NODE_BATCH_SIZE = 20
OUTLINE_CONTENT_VERSION_BATCH_SIZE = 20


class HistoryItem(BaseModel, Generic[T]):
    """History item will be saved to database as json."""

    bid: str
    id: int
    type: str
    children: list["HistoryItem"] = []
    child_count: int = 0
    content_revision: int | None = None

    def to_json(self) -> str:
        """To json."""
        return self.model_dump_json(exclude_none=True)

    @classmethod
    def from_json(cls, json: str) -> "HistoryItem":
        """From json to history item."""
        return cls.model_validate_json(json)


def normalize_outline_content(content: str | None) -> str:
    """Keep authored differences except platform-specific line endings."""
    return (content or "").replace("\r\n", "\n").replace("\r", "\n")


def _outline_nodes(history: HistoryItem) -> Iterator[HistoryItem]:
    pending = [history]
    while pending:
        node = pending.pop()
        if node.type == "outline":
            yield node
        pending.extend(node.children)


def outline_content_revisions(history: HistoryItem) -> dict[str, int]:
    """Read recorded content revisions without loading lesson bodies or history."""
    return {
        node.bid: node.content_revision
        for node in _outline_nodes(history)
        if isinstance(node.content_revision, int) and node.content_revision > 0
    }


def _get_latest_draft_log(
    shifu_bid: str, for_update: bool = False
) -> LogDraftStruct | None:
    query = LogDraftStruct.query.filter_by(
        shifu_bid=shifu_bid,
        deleted=0,
    ).order_by(LogDraftStruct.id.desc())
    if for_update:
        query = query.with_for_update()
    return query.first()


def iter_outline_item_versions_desc(
    shifu_bid: str,
    outline_bid: str,
    *,
    batch_size: int = 200,
    max_rows: int | None = None,
    max_id: int | None = None,
) -> Iterator[DraftOutlineItem]:
    """Yield draft outline versions newest-first in buffered keyset batches.

    Replaces yield_per/stream_results for these scans: a server-side cursor
    left unexhausted by an early ``break`` keeps unread rows on the wire, and
    draining them later is a long, interruptible IO that can return a
    half-read connection to the pool (protocol desync - the ResourceClosedError
    / 2014 Command Out of Sync family seen in production). Buffered
    LIMIT batches are fully consumed per round-trip, so callers may stop
    iterating at any point without leaving connection state behind. Keyset
    pagination (id < last seen) keeps deep pages as cheap as the first one.
    """
    last_id: int | None = None
    yielded = 0
    while True:
        query = DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.outline_item_bid == outline_bid,
            DraftOutlineItem.deleted == 0,
        )
        if last_id is not None:
            query = query.filter(DraftOutlineItem.id < last_id)
        if max_id is not None:
            query = query.filter(DraftOutlineItem.id <= max_id)
        limit = batch_size
        if max_rows is not None:
            limit = min(batch_size, max_rows - yielded)
            if limit <= 0:
                return
        batch = query.order_by(DraftOutlineItem.id.desc()).limit(limit).all()
        if not batch:
            return
        yield from batch
        yielded += len(batch)
        if len(batch) < limit:
            return
        last_id = int(batch[-1].id)


def _get_latest_outline_content_log(
    shifu_bid: str, outline_bid: str
) -> DraftOutlineItem | None:
    latest_version = (
        DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.outline_item_bid == outline_bid,
        )
        .order_by(DraftOutlineItem.id.desc())
        .first()
    )
    if not latest_version:
        return None

    # If the latest revision marks this outline as deleted, treat it as a
    # revision change so clients can notify editors currently on this lesson.
    if latest_version.deleted == 1:
        return latest_version

    latest_log = _get_latest_draft_log(shifu_bid)
    if latest_log is not None:
        node = next(
            (
                node
                for node in _outline_nodes(HistoryItem.from_json(latest_log.struct))
                if node.bid == outline_bid and node.id == latest_version.id
            ),
            None,
        )
        if node is not None and node.content_revision:
            anchor = DraftOutlineItem.query.filter_by(
                id=node.content_revision,
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
                deleted=0,
            ).first()
            if anchor is not None:
                return anchor
    return _outline_content_anchor(latest_version)


def _outline_content_anchor(latest_version: DraftOutlineItem) -> DraftOutlineItem:
    """Recover a missing revision only from rows at or before the exact draft."""
    latest_content = normalize_outline_content(latest_version.content)
    latest_content_revision = latest_version
    recent_active_versions = iter_outline_item_versions_desc(
        latest_version.shifu_bid,
        latest_version.outline_item_bid,
        max_rows=OUTLINE_CONTENT_LOOKBACK_LIMIT,
        max_id=int(latest_version.id),
    )
    for version in recent_active_versions:
        if version.id == latest_version.id:
            continue
        if normalize_outline_content(version.content) != latest_content:
            break
        latest_content_revision = version
    return latest_content_revision


def _outline_content_anchor_ids(outlines: list[DraftOutlineItem]) -> dict[int, int]:
    """Recover anchors with bounded version pages for a batch of exact rows."""
    anchors = {int(row.id): int(row.id) for row in outlines}
    for start in range(0, len(outlines), OUTLINE_CONTENT_NODE_BATCH_SIZE):
        pending = {
            int(row.id): row
            for row in outlines[start : start + OUTLINE_CONTENT_NODE_BATCH_SIZE]
        }
        contents = {
            row_id: normalize_outline_content(row.content)
            for row_id, row in pending.items()
        }
        cursors = {row_id: row_id for row_id in pending}
        for offset in range(
            0, OUTLINE_CONTENT_LOOKBACK_LIMIT, OUTLINE_CONTENT_VERSION_BATCH_SIZE
        ):
            if not pending:
                break
            limit = min(
                OUTLINE_CONTENT_VERSION_BATCH_SIZE,
                OUTLINE_CONTENT_LOOKBACK_LIMIT - offset,
            )
            queries = []
            for row_id, row in pending.items():
                # A LIMIT inside each subquery preserves the per-lesson scan
                # bound; a global limit or window rank can scan all history.
                page = (
                    select(
                        literal(row_id).label("source_id"),
                        DraftOutlineItem.id,
                        DraftOutlineItem.content,
                    )
                    .where(
                        DraftOutlineItem.shifu_bid == row.shifu_bid,
                        DraftOutlineItem.outline_item_bid == row.outline_item_bid,
                        DraftOutlineItem.deleted == 0,
                        DraftOutlineItem.id <= cursors[row_id],
                    )
                    .order_by(DraftOutlineItem.id.desc())
                    .limit(limit)
                    .subquery()
                )
                queries.append(select(page))
            versions = {row_id: [] for row_id in pending}
            for version in db.session.execute(union_all(*queries)).all():
                versions[version.source_id].append(version)
            next_pending = {}
            for row_id, row in pending.items():
                page = sorted(
                    versions[row_id], key=lambda version: version.id, reverse=True
                )
                for version in page:
                    if version.id == row_id:
                        continue
                    if normalize_outline_content(version.content) != contents[row_id]:
                        break
                    anchors[row_id] = int(version.id)
                else:
                    if len(page) == limit:
                        cursors[row_id] = int(page[-1].id) - 1
                        next_pending[row_id] = row
            pending = next_pending
    return anchors


def _initialize_outline_content_revisions(shifu_bid: str, history: HistoryItem) -> None:
    """Initialize legacy structure metadata on a write, never a learner read."""
    missing = [
        node for node in _outline_nodes(history) if node.content_revision is None
    ]
    for start in range(0, len(missing), OUTLINE_CONTENT_NODE_BATCH_SIZE):
        nodes = missing[start : start + OUTLINE_CONTENT_NODE_BATCH_SIZE]
        rows = DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.deleted == 0,
            tuple_(DraftOutlineItem.id, DraftOutlineItem.outline_item_bid).in_(
                [(node.id, node.bid) for node in nodes]
            ),
        ).all()
        anchor_ids = _outline_content_anchor_ids(rows)
        anchors = {(row.id, row.outline_item_bid): anchor_ids[row.id] for row in rows}
        for node in nodes:
            if (node.id, node.bid) in anchors:
                node.content_revision = anchors[node.id, node.bid]


def ensure_outline_content_revisions(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    outlines: list[DraftOutlineItem],
) -> dict[str, int]:
    """Resolve publication revisions and record missing draft metadata atomically."""
    history = get_shifu_history(app, shifu_bid, for_update=True)
    nodes = {node.bid: node for node in _outline_nodes(history)}
    missing = [
        row
        for row in outlines
        if (node := nodes.get(row.outline_item_bid)) is None
        or node.id != row.id
        or node.content_revision is None
    ]
    anchors = _outline_content_anchor_ids(missing)
    revisions = {}
    changed = False
    for row in outlines:
        node = nodes.get(row.outline_item_bid)
        matching_node = node is not None and node.id == row.id
        revision = node.content_revision if matching_node else None
        if revision is None:
            revision = anchors[row.id]
            if matching_node:
                node.content_revision = revision
                changed = True
        revisions[row.outline_item_bid] = revision
    if changed:
        __save_shifu_history(app, user_id, shifu_bid, history)
    return revisions


def _mask_phone_identifier(identifier: str | None) -> str:
    if not identifier:
        return ""
    digits = re.sub(r"\D", "", identifier)
    if len(digits) >= 7:
        return f"{digits[:3]}****{digits[-4:]}"
    if len(digits) >= 2:
        return f"{digits[:1]}****{digits[-1:]}"
    return digits or ""


def _mask_email_identifier(identifier: str | None) -> str:
    if not identifier:
        return ""
    local, _, domain = identifier.partition("@")
    if not domain:
        return _mask_phone_identifier(identifier)
    if not local:
        return f"***@{domain}"
    masked_local = f"{local[:1]}***" if len(local) <= 1 else f"{local[:2]}***"
    return f"{masked_local}@{domain}"


def _mask_contact_identifier(identifier: str | None) -> str:
    if not identifier:
        return ""
    if "@" in identifier:
        return _mask_email_identifier(identifier)
    return _mask_phone_identifier(identifier)


def _build_draft_meta(latest: object) -> dict:
    if not latest:
        return {
            "revision": 0,
            "updated_at": None,
            "updated_user": None,
            "deleted": 0,
        }

    user = (
        UserInfo.query.filter_by(user_bid=latest.updated_user_bid, deleted=0).first()
        if latest.updated_user_bid
        else None
    )
    identifier = user.user_identify if user else ""
    masked_identifier = _mask_contact_identifier(identifier) if identifier else ""
    updated_user = (
        {
            "user_bid": latest.updated_user_bid,
            "phone": masked_identifier,
        }
        if latest.updated_user_bid
        else None
    )
    return {
        "revision": int(latest.id),
        "updated_at": to_utc_iso(latest.updated_at),
        "updated_user": updated_user,
        "deleted": int(getattr(latest, "deleted", 0) or 0),
    }


def get_shifu_draft_revision(
    app: Flask, shifu_bid: str, outline_bid: str | None = None
) -> int:
    """Return shifu draft revision."""
    with app_context_scope(app):
        if outline_bid:
            latest = _get_latest_outline_content_log(shifu_bid, outline_bid)
        else:
            latest = _get_latest_draft_log(shifu_bid)
        return int(latest.id) if latest else 0


def mask_contact_identifier(identifier: str | None) -> str:
    """Public wrapper for contact identifier masking."""
    return _mask_contact_identifier(identifier)


def get_shifu_draft_meta(
    app: Flask,
    shifu_bid: str,
    outline_bid: str | None = None,
) -> dict:
    """Return shifu draft meta."""
    with app_context_scope(app):
        if outline_bid:
            latest = _get_latest_outline_content_log(shifu_bid, outline_bid)
        else:
            latest = _get_latest_draft_log(shifu_bid)
        return _build_draft_meta(latest)


def get_shifu_history(
    app: object, shifu_bid: str, *, for_update: bool = False
) -> HistoryItem:
    """Get shifu history.

    Reads through ``app_context_scope`` so the query joins the caller's
    session and transaction. Every history mutation in this module is a
    read-modify-write of the newest ``LogDraftStruct`` row, so a read that
    pushed its own nested app context would open a *second* session and see
    only committed rows: two nodes written inside one transaction would each
    modify the pre-transaction struct, so the second write would silently drop
    the first, and a child appended after its parent could not find the parent
    at all ("Parent history node not found").

    Args:
        app: Flask application instance
        shifu_bid: Shifu bid
        for_update: Read current committed history while holding the course lock.

    Returns:
        HistoryItem: History item.

    """
    with app_context_scope(app):
        query = LogDraftStruct.query.filter_by(
            shifu_bid=shifu_bid,
        ).order_by(LogDraftStruct.id.desc())
        if for_update:
            query = query.populate_existing().with_for_update()
        shifu_history = query.first()
        if not shifu_history:
            return HistoryItem(bid=shifu_bid, id=0, type="shifu", children=[])
        return HistoryItem.from_json(shifu_history.struct)


def __save_shifu_history(
    app: Flask, user_id: str, shifu_bid: str, history: HistoryItem
) -> LogDraftStruct:
    """Save shifu history.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        history: History item
    Returns:
        None.

    """
    _initialize_outline_content_revisions(shifu_bid, history)
    now = now_utc()
    shifu_history = LogDraftStruct(
        struct_bid=generate_id(app),
        shifu_bid=shifu_bid,
        struct=history.to_json(),
        created_at=now,
        created_user_bid=user_id,
        updated_at=now,
        updated_user_bid=user_id,
    )
    db.session.add(shifu_history)
    db.session.flush()
    return shifu_history


def save_shifu_history(app: Flask, user_id: str, shifu_bid: str, row_id: int) -> None:
    """Save shifu history.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        row_id: Shifu id
    Returns:
        None.

    """
    history = get_shifu_history(app, shifu_bid)
    history.id = row_id
    __save_shifu_history(app, user_id, shifu_bid, history)


def __save_new_item_history(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    item_bid: str,
    row_id: int,
    parent_bid: str,
    item_type: str,
    index: int = 0,
) -> None:
    """Save new item history internal function.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        item_bid: Item bid
        row_id: Item id
        parent_bid: Parent bid
        item_type: Item type
        index: Item index
    Returns:
        None.

    """
    history = get_shifu_history(app, shifu_bid)
    if not parent_bid or parent_bid == "":
        if not history.children:
            history.children = []
        history.children.insert(
            index,
            HistoryItem(
                bid=item_bid,
                id=row_id,
                type=item_type,
                children=[],
                content_revision=row_id if item_type == "outline" else None,
            ),
        )
        __save_shifu_history(app, user_id, shifu_bid, history)
        return

    q = queue.Queue()
    q.put(history)
    parent_found = False
    while not q.empty():
        item = q.get()
        if item.bid == parent_bid:
            item.children.append(
                HistoryItem(
                    bid=item_bid,
                    id=row_id,
                    type=item_type,
                    children=[],
                    content_revision=row_id if item_type == "outline" else None,
                )
            )
            parent_found = True
            break
        for child in item.children:
            q.put(child)

    if not parent_found:
        app.logger.error(
            "Failed to append %s history node because parent is missing | shifu_bid=%s item_bid=%s item_id=%s parent_bid=%s",
            item_type,
            shifu_bid,
            item_bid,
            row_id,
            parent_bid,
        )
        message = f"Parent history node not found for {item_type} {item_bid} under {parent_bid}"
        raise RuntimeError(message)

    __save_shifu_history(app, user_id, shifu_bid, history)


def __delete_item_history(
    app: Flask, user_id: str, shifu_bid: str, item_bid: str
) -> None:
    """Delete item history internal function.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        item_bid: Item bid
    Returns:
        None.

    """
    history = get_shifu_history(app, shifu_bid)
    q = queue.Queue()
    q.put(history)
    while not q.empty():
        item = q.get()
        if item.children and len(item.children) > 0:
            for child in item.children:
                if child.bid == item_bid:
                    item.children.remove(child)
                    break
            for child in item.children:
                q.put(child)
    __save_shifu_history(app, user_id, shifu_bid, history)


def save_new_outline_history(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    outline_bid: str,
    row_id: int,
    parent_bid: str,
    index: int = 0,
) -> None:
    """Save new outline history.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        outline_bid: Outline bid
        row_id: Outline id
        parent_bid: Parent bid
        index: Outline index.

    """
    __save_new_item_history(
        app, user_id, shifu_bid, outline_bid, row_id, parent_bid, "outline", index
    )


def save_outline_history(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    outline_bid: str,
    row_id: int,
    child_count: int = 0,
    *,
    content_revision: int | None = None,
) -> int:
    """Save outline history.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        outline_bid: Outline bid
        row_id: Outline id
        child_count: Optional child count to store on the history item.
        content_revision: New content revision, or None to retain the existing one.

    Returns:
        None.

    """
    history = get_shifu_history(app, shifu_bid)
    q = queue.Queue()
    q.put(history)
    while not q.empty():
        item = q.get()
        if item.type == "outline" and item.bid == outline_bid:
            item.id = row_id
            if content_revision is not None:
                item.content_revision = content_revision
            if child_count > 0:
                item.child_count = child_count
            break
        for child in item.children:
            q.put(child)
    log = __save_shifu_history(app, user_id, shifu_bid, history)
    return int(log.id) if log else 0


def delete_outline_history(
    app: Flask, user_id: str, shifu_bid: str, outline_bid: str
) -> None:
    """Delete outline history.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        outline_bid: Outline bid
    Returns:
        None.

    """
    __delete_item_history(app, user_id, shifu_bid, outline_bid)


def save_outline_tree_history(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    outline_tree: list[HistoryItem],
    shifu_id: int | None = None,
    *,
    for_update: bool = False,
) -> None:
    """Save outline tree history.

    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        outline_tree: Outline tree
        shifu_id: Optional shifu database id to ensure root node id is correct
        for_update: Preserve current history even in an older read snapshot.

    Returns:
        None.

    """
    history = (
        get_shifu_history(app, shifu_bid, for_update=True)
        if for_update
        else get_shifu_history(app, shifu_bid)
    )
    previous_revisions = outline_content_revisions(history)
    if shifu_id is not None:
        history.id = shifu_id
    q = queue.Queue()
    q.put(history)
    blocks_infos = {}
    while not q.empty():
        item = q.get()
        if not item.children or len(item.children) == 0:
            continue
        first_child = item.children[0]
        if first_child.type == "block":
            blocks_infos[item.bid] = item.children
        elif first_child.type == "outline":
            for child in item.children:
                q.put(child)
    history.children = outline_tree
    for node in _outline_nodes(history):
        if node.content_revision is None:
            node.content_revision = previous_revisions.get(node.bid)
    q.put(history)
    while not q.empty():
        item = q.get()
        if item.bid in blocks_infos:
            item.children = blocks_infos[item.bid]
        else:
            for child in item.children:
                q.put(child)
    __save_shifu_history(app, user_id, shifu_bid, history)
