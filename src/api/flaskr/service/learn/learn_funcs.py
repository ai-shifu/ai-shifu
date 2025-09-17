from flask import Flask
from flaskr.service.learn.learn_dtos import (
    LearnShifuInfoDTO,
    LearnOutlineItemInfoDTO,
    LearnRecordDTO,
    LearnStatus,
)
from flaskr.service.shifu.models import (
    DraftShifu,
    PublishedShifu,
    DraftOutlineItem,
    PublishedOutlineItem,
    LogDraftStruct,
    LogPublishedStruct,
)
from flaskr.service.learn.models import LearnProgressRecord, LearnGeneratedBlock
from flaskr.service.common import raise_error
from flaskr.service.shifu.utils import get_shifu_res_url
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.order.models import Order
from flaskr.service.order.consts import (
    ORDER_STATUS_SUCCESS,
    LEARN_STATUS_LOCKED,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_RESET,
)
import queue
from flaskr.dao import db
from flaskr.service.lesson.const import LESSON_TYPE_NORMAL

STATUS_MAP = {
    LEARN_STATUS_LOCKED: LearnStatus.LOCKED,
    LEARN_STATUS_NOT_STARTED: LearnStatus.NOT_STARTED,
    LEARN_STATUS_IN_PROGRESS: LearnStatus.IN_PROGRESS,
    LEARN_STATUS_COMPLETED: LearnStatus.COMPLETED,
}


def get_shifu_info(app: Flask, shifu_bid: str, preview_mode: bool) -> LearnShifuInfoDTO:
    with app.app_context():
        model = DraftShifu if preview_mode else PublishedShifu
        shifu = (
            model.query.filter(model.shifu_bid == shifu_bid, model.deleted == 0)
            .order_by(model.id.desc())
            .first()
        )
        if not shifu:
            raise_error("SHIFU.SHIFU_NOT_FOUND")
        return LearnShifuInfoDTO(
            bid=shifu.shifu_bid,
            title=shifu.title,
            description=shifu.description,
            avatar=get_shifu_res_url(shifu.avatar_res_bid),
            price=str(shifu.price),
            keywords=shifu.keywords.split(",") if shifu.keywords else [],
        )


def get_outline_item_tree(
    app: Flask, shifu_bid: str, user_bid: str, preview_mode: bool
) -> list[LearnOutlineItemInfoDTO]:
    with app.app_context():
        is_paid = preview_mode
        if preview_mode:
            outline_item_model = DraftOutlineItem
            struct_model = LogDraftStruct
            shifu_model = DraftShifu
        else:
            outline_item_model = PublishedOutlineItem
            struct_model = LogPublishedStruct
            shifu_model = PublishedShifu
        if not is_paid:
            shifu = (
                shifu_model.query.filter(
                    shifu_model.shifu_bid == shifu_bid, shifu_model.deleted == 0
                )
                .order_by(shifu_model.id.desc())
                .first()
            )
            if not shifu:
                raise_error("SHIFU.SHIFU_NOT_FOUND")
            if shifu.price == 0:
                is_paid = True
            else:
                buy_record = (
                    Order.query.filter(
                        Order.user_bid == user_bid,
                        Order.shifu_bid == shifu_bid,
                        Order.status == ORDER_STATUS_SUCCESS,
                    )
                    .order_by(Order.id.desc())
                    .first()
                )
                if not buy_record:
                    is_paid = False
                else:
                    is_paid = True
        struct = (
            struct_model.query.filter(
                struct_model.shifu_bid == shifu_bid, struct_model.deleted == 0
            )
            .order_by(struct_model.id.desc())
            .first()
        )
        if not struct:
            raise_error("SHIFU.SHIFU_STRUCT_NOT_FOUND")
        struct = HistoryItem.from_json(struct.struct)
        outline_items = []
        q = queue.Queue()
        q.put(struct)
        while not q.empty():
            item = q.get()
            if item.type == "outline":
                outline_items.append(item)
            if item.children:
                for child in item.children:
                    q.put(child)
        outline_items_ids = [i.id for i in outline_items]
        outline_items_dbs = outline_item_model.query.filter(
            outline_item_model.id.in_(outline_items_ids),
            outline_item_model.deleted == 0,
        ).all()
        progress_records = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid.in_(outline_items_ids),
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.deleted == 0,
        ).all()
        progress_records_map: dict[str, LearnProgressRecord] = {
            i.outline_item_bid: i for i in progress_records
        }

        def build_outline_item_tree(item: HistoryItem):
            outline_item: DraftOutlineItem | PublishedOutlineItem = next(
                (i for i in outline_items_dbs if i.id == item.id), None
            )
            if not outline_item:
                return None
            progress_record = progress_records_map.get(
                outline_item.outline_item_bid, None
            )
            if not progress_record:
                if is_paid:
                    status = LEARN_STATUS_NOT_STARTED
                elif outline_item.type == LESSON_TYPE_NORMAL:
                    status = LEARN_STATUS_LOCKED
                else:
                    status = LEARN_STATUS_NOT_STARTED
            else:
                status = progress_record.status
            outline_item_info = LearnOutlineItemInfoDTO(
                bid=outline_item.outline_item_bid,
                position=outline_item.position,
                title=outline_item.title,
                status=STATUS_MAP.get(status, LearnStatus.LOCKED),
                children=[],
            )
            if item.children:
                for child in item.children:
                    child_info = build_outline_item_tree(child)
                    if child_info:
                        outline_item_info.children.append(child_info)
            return outline_item_info

        outline_items = [build_outline_item_tree(i) for i in outline_items]
        return outline_items


def get_learn_record(
    app: Flask, shifu_bid: str, user_bid: str, preview_mode: bool
) -> list[LearnRecordDTO]:
    with app.app_context():
        pass


def reset_learn_record(
    app: Flask, shifu_bid: str, outline_bid: str, user_bid: str
) -> bool:
    with app.app_context():
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
        ).update({"status": LEARN_STATUS_RESET})
        db.session.commit()
        return True


def handle_reaction(
    app: Flask, shifu_bid: str, user_bid: str, generated_block_bid: str, action: str
) -> bool:
    with app.app_context():
        generated_block = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.user_bid == user_bid,
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.generated_block_bid == generated_block_bid,
            LearnGeneratedBlock.deleted == 0,
        ).first()
        if not generated_block:
            raise_error("LEARN.GENERATED_BLOCK_NOT_FOUND")
        if action == "like":
            generated_block.liked = 1
        if action == "dislike":
            generated_block.liked = -1
        db.session.commit()
        return True
