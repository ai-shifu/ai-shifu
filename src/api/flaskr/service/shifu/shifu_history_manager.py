from flask import Flask
from typing import Generic, TypeVar, List
from pydantic import BaseModel
from .models import ShifuLogDraftStruct
from flaskr.dao import db
from flaskr.util import generate_id
import queue
from datetime import datetime

"""
save shifu history to database

format
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

T = TypeVar("T", bound="HistoryItem")


class HistoryItem(BaseModel, Generic[T]):
    bid: str
    id: int
    type: str
    children: List["HistoryItem"] = []

    def to_json(self):
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json: str):
        return cls.model_validate_json(json)


class HistoryInfo(BaseModel):
    bid: str
    id: int


def get_shifu_history(app, shifu_bid: str) -> HistoryItem:
    with app.app_context():
        shifu_history = (
            ShifuLogDraftStruct.query.filter_by(
                shifu_bid=shifu_bid,
            )
            .order_by(ShifuLogDraftStruct.created_at.desc())
            .first()
        )
        if not shifu_history:
            init_history = HistoryItem(bid=shifu_bid, id=0, type="shifu", children=[])
            return init_history
        return HistoryItem.from_json(shifu_history.struct)


def __save_shifu_history(
    app: Flask, user_id: str, shifu_bid: str, history: HistoryItem
):
    now = datetime.now()
    shifu_history = ShifuLogDraftStruct(
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
    __save_new_item_history(
        app, user_id, shifu_bid, block_bid, id, parent_bid, "block", index
    )


def save_outline_history(
    app: Flask, user_id: str, shifu_bid: str, outline_bid: str, id: int
):
    history = get_shifu_history(app, shifu_bid)
    q = queue.Queue()
    q.put(history)
    while not q.empty():
        item = q.get()
        if item.bid == outline_bid:
            item.id = id
            break
        for child in item.children:
            q.put(child)
    __save_shifu_history(app, user_id, shifu_bid, history)


def delete_outline_history(app: Flask, user_id: str, shifu_bid: str, outline_bid: str):
    __delete_item_history(app, user_id, shifu_bid, outline_bid)


def delete_block_history(app: Flask, user_id: str, shifu_bid: str, block_bid: str):
    __delete_item_history(app, user_id, shifu_bid, block_bid)


def save_outline_tree_history(
    app: Flask, user_id: str, shifu_bid: str, outline_tree: List[HistoryItem]
):
    history = get_shifu_history(app, shifu_bid)
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
