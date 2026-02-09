"""Query helpers for the teacher-facing analytics dashboard.

Hard constraint: do not use database join queries. Load parent records first, then
load child records via `IN (...)` and merge in Python.
"""

from __future__ import annotations

from typing import Dict, List

from flask import Flask

from flaskr.service.common.models import raise_error
from flaskr.service.dashboard.dtos import DashboardOutlineDTO
from flaskr.service.shifu.funcs import shifu_permission_verification
from flaskr.service.shifu.models import LogPublishedStruct, PublishedOutlineItem
from flaskr.service.shifu.shifu_history_manager import HistoryItem


def dashboard_healthcheck(app: Flask) -> bool:
    """Small helper to verify the dashboard module is loaded."""
    with app.app_context():
        return True


def require_shifu_view_permission(app: Flask, user_id: str, shifu_bid: str) -> None:
    """Raise if the user does not have view permission for this shifu."""
    with app.app_context():
        allowed = shifu_permission_verification(app, user_id, shifu_bid, "view")
        if not allowed:
            raise_error("server.shifu.noPermission")


def _collect_outline_nodes_in_order(struct: HistoryItem) -> List[HistoryItem]:
    nodes: List[HistoryItem] = []

    def walk(item: HistoryItem) -> None:
        if item.type == "outline":
            nodes.append(item)
        for child in item.children or []:
            walk(child)

    for child in struct.children or []:
        walk(child)
    return nodes


def load_published_outlines(app: Flask, shifu_bid: str) -> List[DashboardOutlineDTO]:
    """Load published outline items for a shifu in the struct order."""
    with app.app_context():
        struct_row: LogPublishedStruct | None = (
            LogPublishedStruct.query.filter(
                LogPublishedStruct.shifu_bid == shifu_bid,
                LogPublishedStruct.deleted == 0,
            )
            .order_by(LogPublishedStruct.id.desc())
            .first()
        )
        if not struct_row or not struct_row.struct:
            raise_error("server.shifu.shifuStructNotFound")

        struct = HistoryItem.from_json(struct_row.struct)
        outline_nodes = _collect_outline_nodes_in_order(struct)
        outline_ids = [node.id for node in outline_nodes if node.id]
        if not outline_ids:
            return []

        outline_rows: List[PublishedOutlineItem] = (
            PublishedOutlineItem.query.filter(
                PublishedOutlineItem.id.in_(outline_ids),
                PublishedOutlineItem.shifu_bid == shifu_bid,
                PublishedOutlineItem.deleted == 0,
            )
            .order_by(PublishedOutlineItem.id.asc())
            .all()
        )
        outline_by_id: Dict[int, PublishedOutlineItem] = {
            row.id: row for row in outline_rows
        }

        result: List[DashboardOutlineDTO] = []
        for node in outline_nodes:
            row = outline_by_id.get(node.id)
            if not row:
                continue
            result.append(
                DashboardOutlineDTO(
                    outline_item_bid=row.outline_item_bid or node.bid,
                    title=row.title or "",
                    type=int(row.type or 0),
                    hidden=bool(row.hidden),
                    parent_bid=row.parent_bid or "",
                    position=row.position or "",
                )
            )
        return result
