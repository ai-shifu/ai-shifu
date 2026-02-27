"""
Shifu history manager

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

from flask import Flask
from typing import Generic, TypeVar, List
from pydantic import BaseModel
from .models import LogDraftStruct
from flaskr.dao import db
from flaskr.util import generate_id
import queue
from datetime import datetime
import re
from flaskr.service.user.models import UserInfo

T = TypeVar("T", bound="HistoryItem")


class HistoryItem(BaseModel, Generic[T]):
    """
    History item
    will be saved to database as json
    """

    bid: str
    id: int
    type: str
    children: List["HistoryItem"] = []
    child_count: int = 0

    def to_json(self):
        """
        to json
        """
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json: str):
        """
        from json to history item
        """
        return cls.model_validate_json(json)


class HistoryInfo(BaseModel):
    """
    History info
    will be saved to database as json
    format:
    {
        "bid": "bid",
        "id": "id",
    }
    bid: business id (outline_bid, block_bid, shifu_bid)
    id: id
    """

    bid: str
    id: int


def _get_latest_draft_log(shifu_bid: str):
    return (
        LogDraftStruct.query.filter_by(
            shifu_bid=shifu_bid,
        )
        .order_by(LogDraftStruct.id.desc())
        .first()
    )


def _mask_phone_identifier(identifier: str) -> str:
    if not identifier:
        return ""
    digits = re.sub(r"\D", "", identifier)
    if len(digits) >= 7:
        return f"{digits[:3]}****{digits[-4:]}"
    if len(digits) >= 2:
        return f"{digits[:1]}****{digits[-1:]}"
    return digits or ""


def _mask_email_identifier(identifier: str) -> str:
    if not identifier:
        return ""
    local, _, domain = identifier.partition("@")
    if not domain:
        return _mask_phone_identifier(identifier)
    if not local:
        return f"***@{domain}"
    if len(local) <= 1:
        masked_local = f"{local[:1]}***"
    else:
        masked_local = f"{local[:2]}***"
    return f"{masked_local}@{domain}"


def _mask_contact_identifier(identifier: str) -> str:
    if not identifier:
        return ""
    if "@" in identifier:
        return _mask_email_identifier(identifier)
    return _mask_phone_identifier(identifier)


def get_shifu_draft_revision(app: Flask, shifu_bid: str) -> int:
    with app.app_context():
        latest = _get_latest_draft_log(shifu_bid)
        return int(latest.id) if latest else 0


def get_shifu_draft_meta(app: Flask, shifu_bid: str) -> dict:
    with app.app_context():
        latest = _get_latest_draft_log(shifu_bid)
        if not latest:
            return {"revision": 0, "updated_at": None, "updated_user": None}

        user = (
            UserInfo.query.filter_by(
                user_bid=latest.updated_user_bid, deleted=0
            ).first()
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
            "updated_at": latest.updated_at,
            "updated_user": updated_user,
        }

def get_shifu_history(app, shifu_bid: str) -> HistoryItem:
    """
    Get shifu history
    Args:
        app: Flask application instance
        shifu_bid: Shifu bid
    Returns:
        HistoryItem: History item
    """
    with app.app_context():
        shifu_history = (
            LogDraftStruct.query.filter_by(
                shifu_bid=shifu_bid,
            )
            .order_by(LogDraftStruct.id.desc())
            .first()
        )
        if not shifu_history:
            init_history = HistoryItem(bid=shifu_bid, id=0, type="shifu", children=[])
            return init_history
        return HistoryItem.from_json(shifu_history.struct)


def __save_shifu_history(
    app: Flask, user_id: str, shifu_bid: str, history: HistoryItem
):
    """
    Save shifu history
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        history: History item
    Returns:
        None
    """
    now = datetime.now()
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


def save_shifu_history(app: Flask, user_id: str, shifu_bid: str, id: int):
    """
    Save shifu history
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        id: Shifu id
    Returns:
        None
    """
    history = get_shifu_history(app, shifu_bid)
    history.id = id
    __save_shifu_history(app, user_id, shifu_bid, history)


def save_blocks_history(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    outline_bid: str,
    block_infos: List[HistoryInfo],
):
    """
    Save blocks history
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        outline_bid: Outline bid
        block_infos: Block infos
    """
    history = get_shifu_history(app, shifu_bid)
    q = queue.Queue()
    q.put(history)
    while not q.empty():
        item = q.get()
        if item.bid == outline_bid:
            item.children = [
                HistoryItem(
                    bid=block_info.bid, id=block_info.id, type="block", children=[]
                )
                for block_info in block_infos
            ]
            break
        for child in item.children:
            q.put(child)
    __save_shifu_history(app, user_id, shifu_bid, history)


def __save_new_item_history(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    item_bid: str,
    id: int,
    parent_bid: str,
    type: str,
    index: int = 0,
):
    """
    Save new item history
    internal function
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        item_bid: Item bid
        id: Item id
        parent_bid: Parent bid
        type: Item type
        index: Item index
    Returns:
        None
    """
    history = get_shifu_history(app, shifu_bid)
    if not parent_bid or parent_bid == "":
        if not history.children:
            history.children = []
        history.children.insert(
            index, HistoryItem(bid=item_bid, id=id, type=type, children=[])
        )
        __save_shifu_history(app, user_id, shifu_bid, history)
        return

    q = queue.Queue()
    q.put(history)
    while not q.empty():
        item = q.get()
        if item.bid == parent_bid:
            item.children.append(
                HistoryItem(bid=item_bid, id=id, type=type, children=[])
            )
            break
        for child in item.children:
            q.put(child)

    __save_shifu_history(app, user_id, shifu_bid, history)


def __delete_item_history(app: Flask, user_id: str, shifu_bid: str, item_bid: str):
    """
    Delete item history
    internal function
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        item_bid: Item bid
    Returns:
        None
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
    id: int,
    parent_bid: str,
    index: int = 0,
):
    """
    Save new outline history
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        outline_bid: Outline bid
        id: Outline id
        parent_bid: Parent bid
        index: Outline index
    """
    __save_new_item_history(
        app, user_id, shifu_bid, outline_bid, id, parent_bid, "outline", index
    )


def save_new_block_history(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    block_bid: str,
    id: int,
    parent_bid: str,
    index: int = 0,
):
    """
    Save new block history
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        block_bid: Block bid
        id: Block id
        parent_bid: Parent bid
        index: Block index
    Returns:
        None
    """
    __save_new_item_history(
        app, user_id, shifu_bid, block_bid, id, parent_bid, "block", index
    )


def save_outline_history(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    outline_bid: str,
    id: int,
    child_count: int = 0,
):
    """
    Save outline history
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        outline_bid: Outline bid
        id: Outline id
    Returns:
        None
    """
    history = get_shifu_history(app, shifu_bid)
    q = queue.Queue()
    q.put(history)
    while not q.empty():
        item = q.get()
        if item.bid == outline_bid:
            item.id = id
            if child_count > 0:
                item.child_count = child_count
            break
        for child in item.children:
            q.put(child)
    __save_shifu_history(app, user_id, shifu_bid, history)


def delete_outline_history(app: Flask, user_id: str, shifu_bid: str, outline_bid: str):
    """
    Delete outline history
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        outline_bid: Outline bid
    Returns:
        None
    """
    __delete_item_history(app, user_id, shifu_bid, outline_bid)


def delete_block_history(app: Flask, user_id: str, shifu_bid: str, block_bid: str):
    """
    Delete block history
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        block_bid: Block bid
    Returns:
        None
    """
    __delete_item_history(app, user_id, shifu_bid, block_bid)


def save_outline_tree_history(
    app: Flask,
    user_id: str,
    shifu_bid: str,
    outline_tree: List[HistoryItem],
    shifu_id: int = None,
):
    """
    Save outline tree history
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_bid: Shifu bid
        outline_tree: Outline tree
        shifu_id: Optional shifu database id to ensure root node id is correct
    Returns:
        None
    """
    history = get_shifu_history(app, shifu_bid)
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
    q.put(history)
    while not q.empty():
        item = q.get()
        if item.bid in blocks_infos:
            item.children = blocks_infos[item.bid]
        else:
            for child in item.children:
                q.put(child)
    __save_shifu_history(app, user_id, shifu_bid, history)
