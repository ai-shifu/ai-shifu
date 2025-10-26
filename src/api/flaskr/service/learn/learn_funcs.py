from decimal import Decimal
from markdown_flow import (
    InteractionParser,
)
from flask import Flask, request
from flaskr.service.learn.learn_dtos import (
    LearnShifuInfoDTO,
    LearnOutlineItemInfoDTO,
    LearnRecordDTO,
    LearnStatus,
    GeneratedBlockDTO,
    BlockType,
    LikeStatus,
    LearnOutlineItemsWithBannerInfoDTO,
    LearnBannerInfoDTO,
    OutlineType,
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
from flaskr.service.order.models import Order, BannerInfo
from flaskr.i18n import _
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
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_CONTENT_VALUE,
    BLOCK_TYPE_BUTTON_VALUE,
    BLOCK_TYPE_INPUT_VALUE,
    BLOCK_TYPE_OPTIONS_VALUE,
    BLOCK_TYPE_GOTO_VALUE,
    BLOCK_TYPE_PAYMENT_VALUE,
    BLOCK_TYPE_LOGIN_VALUE,
    BLOCK_TYPE_BREAK_VALUE,
    BLOCK_TYPE_PHONE_VALUE,
    BLOCK_TYPE_CHECKCODE_VALUE,
)
from flaskr.service.learn.const import CONTEXT_INTERACTION_NEXT, ROLE_TEACHER
from flaskr.service.shifu.models import DraftBlock, PublishedBlock
from typing import Union
from flaskr.service.profile.profile_manage import get_profile_item_definition_list
from flaskr.service.shifu.block_to_mdflow_adapter import convert_block_to_mdflow
from flaskr.service.shifu.dtos import BlockDTO
from flaskr.service.shifu.adapter import generate_block_dto_from_model_internal
from flaskr.service.shifu.consts import (
    UNIT_TYPE_VALUE_TRIAL,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_GUEST,
)

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
            raise_error("server.shifu.shifuNotFound")
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
) -> LearnOutlineItemsWithBannerInfoDTO:
    with app.app_context():
        outline_type_map = {
            UNIT_TYPE_VALUE_TRIAL: OutlineType.TRIAL,
            UNIT_TYPE_VALUE_NORMAL: OutlineType.NORMAL,
            UNIT_TYPE_VALUE_GUEST: OutlineType.GUEST,
        }
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
                raise_error("server.shifu.shifuNotFound")
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
            raise_error("server.shifu.shifuStructNotFound")
        struct = HistoryItem.from_json(struct.struct)
        outline_items: list[HistoryItem] = []
        q = queue.Queue()
        q.put(struct)
        while not q.empty():
            item: HistoryItem = q.get()
            if item.type == "outline":
                outline_items.append(item)
            if item.children:
                for child in item.children:
                    q.put(child)
        outline_items_ids = [i.id for i in outline_items]
        outline_items_bids = [i.bid for i in outline_items]
        outline_items_dbs = outline_item_model.query.filter(
            outline_item_model.id.in_(outline_items_ids),
            outline_item_model.deleted == 0,
        ).all()
        progress_records = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid.in_(outline_items_bids),
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
            if not outline_item or outline_item.hidden == 1:
                return None
            progress_record = progress_records_map.get(
                outline_item.outline_item_bid, None
            )
            if not progress_record:
                status = LEARN_STATUS_NOT_STARTED
            else:
                status = progress_record.status
                if status == LEARN_STATUS_LOCKED:
                    status = LEARN_STATUS_NOT_STARTED
            outline_item_info = LearnOutlineItemInfoDTO(
                bid=outline_item.outline_item_bid,
                position=outline_item.position,
                title=outline_item.title,
                status=STATUS_MAP.get(status, LearnStatus.NOT_STARTED),
                type=outline_type_map.get(outline_item.type, OutlineType.NORMAL),
                is_paid=is_paid,
                children=[],
            )
            if item.children:
                for child in item.children:
                    child_info = build_outline_item_tree(child)
                    if child_info:
                        outline_item_info.children.append(child_info)
            return outline_item_info

        outline_items = []
        for i in struct.children:
            outline_item_info = build_outline_item_tree(i)
            if outline_item_info:
                outline_items.append(outline_item_info)
        banner_info_dto = None

        banner_info = BannerInfo.query.filter(
            BannerInfo.course_id == shifu_bid,
            BannerInfo.deleted == 0,
        ).first()
        add_banner = banner_info and banner_info.show_banner == 1
        add_lesson_banner = banner_info and banner_info.show_lesson_banner == 1

        if not add_banner and not add_lesson_banner:
            return LearnOutlineItemsWithBannerInfoDTO(
                banner_info=banner_info_dto,
                outline_items=outline_items,
            )
        is_paid = shifu.price == Decimal(0)
        if not is_paid:
            buy_record = Order.query.filter(
                Order.user_bid == user_bid,
                Order.shifu_bid == shifu_bid,
                Order.status == ORDER_STATUS_SUCCESS,
            ).first()
            is_paid = buy_record and buy_record.status == ORDER_STATUS_SUCCESS

        if not is_paid:
            if add_banner:
                banner_info_dto = LearnBannerInfoDTO(
                    title=_("server.banner.bannerTitle"),
                    pop_up_title=_("server.banner.bannerPopUpTitle"),
                    pop_up_content=_("server.banner.bannerPopUpContent"),
                    pop_up_confirm_text=_("server.banner.bannerPopUpConfirmText"),
                    pop_up_cancel_text=_("server.banner.bannerPopUpCancelText"),
                )
        return LearnOutlineItemsWithBannerInfoDTO(
            banner_info=banner_info_dto,
            outline_items=outline_items,
        )


def get_mdflow(
    app: Flask,
    mdflow: str,
    block: Union[DraftBlock, PublishedBlock],
    variable_map: dict[str, str],
) -> str:
    # if mdflow is not json, return mdflow
    if not mdflow.startswith("{"):
        return mdflow
    # if mdflow is json, parse it
    try:
        if not block:
            return mdflow
        block_dto: BlockDTO = generate_block_dto_from_model_internal(
            block, convert_html=True
        )
        mdflow = convert_block_to_mdflow(block_dto, variable_map)
        return mdflow

    except Exception:
        return mdflow


def get_learn_record(
    app: Flask, shifu_bid: str, outline_bid: str, user_bid: str, preview_mode: bool
) -> LearnRecordDTO:
    with app.app_context():
        block_model: Union[DraftBlock, PublishedBlock] = (
            DraftBlock if preview_mode else PublishedBlock
        )
        variable_definitions = get_profile_item_definition_list(app, shifu_bid)
        variable_map = {
            variable_definition.profile_id: variable_definition.profile_key
            for variable_definition in variable_definitions
        }
        progress_record = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        ).first()
        if not progress_record:
            return LearnRecordDTO(
                records=[],
                interaction="",
            )
        app.logger.info(f"progress_record: {progress_record.progress_record_bid}")
        generated_blocks: list[LearnGeneratedBlock] = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.user_bid == user_bid,
                LearnGeneratedBlock.shifu_bid == shifu_bid,
                LearnGeneratedBlock.progress_record_bid
                == progress_record.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid == outline_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
            )
            .order_by(LearnGeneratedBlock.position.asc(), LearnGeneratedBlock.id.asc())
            .all()
        )

        records: list[GeneratedBlockDTO] = []
        interaction = ""
        BLOCK_TYPE_MAP = {
            BLOCK_TYPE_MDCONTENT_VALUE: BlockType.CONTENT,
            BLOCK_TYPE_MDINTERACTION_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_MDERRORMESSAGE_VALUE: BlockType.ERROR_MESSAGE,
            BLOCK_TYPE_MDASK_VALUE: BlockType.ASK,
            BLOCK_TYPE_MDANSWER_VALUE: BlockType.ANSWER,
            BLOCK_TYPE_CONTENT_VALUE: BlockType.CONTENT,
            BLOCK_TYPE_BUTTON_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_INPUT_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_OPTIONS_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_GOTO_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_PAYMENT_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_LOGIN_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_BREAK_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_PHONE_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_CHECKCODE_VALUE: BlockType.INTERACTION,
        }
        LIKE_STATUS_MAP = {
            1: LikeStatus.LIKE,
            -1: LikeStatus.DISLIKE,
            0: LikeStatus.NONE,
        }
        block_ids = [generated_block.block_bid for generated_block in generated_blocks]
        blocks = block_model.query.filter(
            block_model.block_bid.in_(block_ids), block_model.deleted == 0
        ).all()
        block_map: dict[str, Union[DraftBlock, PublishedBlock]] = {
            i.block_bid: i for i in blocks
        }
        for generated_block in generated_blocks:
            block_type = BLOCK_TYPE_MAP.get(generated_block.type, BlockType.CONTENT)
            if block_type == BlockType.ASK and generated_block.role == ROLE_TEACHER:
                block_type = BlockType.ANSWER

            record = GeneratedBlockDTO(
                generated_block.generated_block_bid,
                generated_block.generated_content
                if block_type
                in (
                    BlockType.CONTENT,
                    BlockType.ERROR_MESSAGE,
                    BlockType.ASK,
                    BlockType.ANSWER,
                )
                else get_mdflow(
                    app,
                    generated_block.block_content_conf,
                    block_map.get(generated_block.block_bid, None),
                    variable_map,
                ),
                LIKE_STATUS_MAP.get(generated_block.liked, LikeStatus.NONE),
                block_type,
                generated_block.generated_content
                if block_type == BlockType.INTERACTION
                else "",
            )
            records.append(record)
        if len(records) > 0:
            last_record = records[-1]
            if last_record.block_type == BlockType.INTERACTION:
                interaction_parser = InteractionParser()
                parsed_interaction = interaction_parser.parse(last_record.content)
                if (
                    parsed_interaction.get("buttons")
                    and len(parsed_interaction.get("buttons")) > 0
                ):
                    for button in parsed_interaction.get("buttons"):
                        if button.get("value") == "_sys_pay":
                            pass
                        if button.get("value") == "_sys_login":
                            if bool(request.user.mobile):
                                records.remove(last_record)
        if progress_record.status == LEARN_STATUS_COMPLETED and interaction == "":
            interaction = (
                "?["
                + _("server.learn.nextChapter")
                + "//"
                + CONTEXT_INTERACTION_NEXT
                + "]"
            )
            records.append(
                GeneratedBlockDTO(
                    "next",
                    interaction,
                    LikeStatus.NONE,
                    BlockType.INTERACTION,
                    "",
                )
            )
        return LearnRecordDTO(
            records=records,
            interaction=interaction,
        )


def reset_learn_record(
    app: Flask, shifu_bid: str, outline_bid: str, user_bid: str
) -> bool:
    with app.app_context():
        progress_records = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        ).all()
        for progress_record in progress_records:
            progress_record.status = LEARN_STATUS_RESET

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
            LearnGeneratedBlock.status == 1,
        ).first()
        if not generated_block:
            raise_error("server.learn.generatedBlockNotFound")
        if action not in ["like", "dislike", "none"]:
            raise_error("server.learn.invalidAction")
        if action == "like":
            generated_block.liked = 1
        if action == "dislike":
            generated_block.liked = -1
        if action == "none":
            generated_block.liked = 0
        db.session.commit()
        return True
