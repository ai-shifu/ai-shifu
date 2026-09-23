"""Read the exact course version taught by a published or draft structure."""

from __future__ import annotations

from dataclasses import dataclass

from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem


@dataclass(frozen=True)
class CourseCompletionSnapshot:
    """Version-pinned rows and the visible leaves in their runtime tree."""

    course: DraftShifu | PublishedShifu
    outline_items: list[DraftOutlineItem | PublishedOutlineItem]
    visible_leaf_outline_bids: list[str]


def load_course_completion_snapshot(
    shifu_bid: str, *, published: bool
) -> CourseCompletionSnapshot:
    """Load a checked snapshot without changing Flask's current app context.

    Learners use the latest published structure; unpublished author previews
    use the latest draft structure. The IDs in that structure, not the latest
    row for each business ID, decide which text and prompt belong to the run.
    """
    log_model = LogPublishedStruct if published else LogDraftStruct
    course_model = PublishedShifu if published else DraftShifu
    outline_model = PublishedOutlineItem if published else DraftOutlineItem
    log = (
        log_model.query.filter(
            log_model.shifu_bid == shifu_bid,
        )
        .order_by(log_model.id.desc())
        .first()
    )
    if log is None or log.deleted != 0:
        message = "course structure snapshot is missing"
        raise ValueError(message)
    root = HistoryItem.from_json(log.struct)
    if root.type != "shifu" or root.bid != shifu_bid or root.id <= 0:
        message = "course structure root is invalid"
        raise ValueError(message)
    course = course_model.query.filter(
        course_model.id == root.id,
        course_model.shifu_bid == shifu_bid,
        course_model.deleted == 0,
    ).first()
    if course is None:
        message = "course snapshot row is missing or mismatched"
        raise ValueError(message)

    nodes: list[tuple[HistoryItem, str]] = []
    bids: set[str] = set()
    ids: set[int] = set()

    def gather(node: HistoryItem, parent_bid: str) -> None:
        if node.type != "outline" or not node.bid or node.id <= 0:
            message = "course outline structure is invalid"
            raise ValueError(message)
        if node.bid in bids or node.id in ids:
            message = "course outline structure has duplicate nodes"
            raise ValueError(message)
        bids.add(node.bid)
        ids.add(node.id)
        nodes.append((node, parent_bid))
        for child in node.children:
            gather(child, node.bid)

    for child in root.children:
        gather(child, "")
    if not nodes:
        message = "course has no outline nodes"
        raise ValueError(message)

    rows = outline_model.query.filter(
        outline_model.id.in_(ids),
        outline_model.deleted == 0,
    ).all()
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(ids):
        message = "course outline snapshot rows are missing"
        raise ValueError(message)
    for node, parent_bid in nodes:
        row = by_id[node.id]
        if (
            row.shifu_bid != shifu_bid
            or row.outline_item_bid != node.bid
            or str(row.parent_bid or "") != parent_bid
        ):
            message = "course outline snapshot row is mismatched"
            raise ValueError(message)

    visible_leaves: list[str] = []

    def visit(node: HistoryItem) -> None:
        row = by_id[node.id]
        if bool(row.hidden):
            return
        for child in node.children:
            visit(child)
        # Runtime lesson eligibility uses the raw structure's children, even
        # when every child is hidden and later pruned from the visible tree.
        if not node.children:
            visible_leaves.append(node.bid)

    for child in root.children:
        visit(child)
    if not visible_leaves:
        message = "course has no visible lessons"
        raise ValueError(message)
    return CourseCompletionSnapshot(
        course=course,
        outline_items=[by_id[node.id] for node, _ in nodes],
        visible_leaf_outline_bids=visible_leaves,
    )
