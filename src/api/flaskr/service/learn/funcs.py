from flask import Flask
from typing import Union
from flaskr.framework.plugin.plugin_manager import extensible
from flaskr.service.learn.const import (
    ROLE_VALUES,
)
from flaskr.service.learn.dtos import (
    StudyRecordDTO,
    StudyRecordItemDTO,
    ScriptInfoDTO,
)
import json
from flaskr.service.order.consts import (
    LEARN_STATUS_RESET,
)

from flaskr.service.lesson.const import (
    LESSON_TYPE_TRIAL,
)
from flaskr.dao import db

from flaskr.service.learn.models import (
    LearnProgressRecord,
    LearnGeneratedBlock,
)
from flaskr.service.learn.plugin import handle_ui
from flaskr.api.langfuse import MockClient
from flaskr.service.user.repository import load_user_aggregate
from flaskr.service.common import raise_error
from flaskr.service.shifu.shifu_struct_manager import (
    get_outline_item_dto,
    get_shifu_struct,
    ShifuInfoDto,
    ShifuOutlineItemDto,
    HistoryItem,
    get_shifu_dto,
)
from flaskr.service.shifu.models import (
    DraftBlock,
    PublishedBlock,
)
from flaskr.service.shifu.adapter import (
    BlockDTO,
    generate_block_dto_from_model_internal,
)
from flaskr.service.shifu.consts import BLOCK_TYPE_CONTENT
import queue
from flaskr.service.learn.output.handle_output_continue import _handle_output_continue


@extensible
def get_study_record(
    app: Flask, user_id: str, lesson_id: str, preview_mode: bool = False
) -> StudyRecordDTO:
    """
    Get the study record
    the study record is used to display the study record in the client
    Args:
        app: Flask application instance
        user_id: User id
        lesson_id: Lesson id
        preview_mode: Preview mode
    Returns:
        StudyRecordDTO
    """
    with app.app_context():
        block_model: Union[DraftBlock, PublishedBlock] = (
            DraftBlock if preview_mode else PublishedBlock
        )
        outline_item: ShifuOutlineItemDto = get_outline_item_dto(
            app, lesson_id, preview_mode
        )
        ret = StudyRecordDTO([])
        if not outline_item:
            return ret
        shifu_info: ShifuInfoDto = get_shifu_dto(
            app, outline_item.shifu_bid, preview_mode
        )
        if not shifu_info:
            return ret
        ret.teacher_avatar = shifu_info.avatar
        shifu_struct: HistoryItem = get_shifu_struct(
            app, outline_item.shifu_bid, preview_mode
        )
        if not shifu_struct:
            return ret

        q = queue.Queue()
        q.put(shifu_struct)
        lesson_info: HistoryItem = None
        while not q.empty():
            item: HistoryItem = q.get()
            if item.bid == lesson_id:
                lesson_info = item
                break
            if item.children:
                for child in item.children:
                    q.put(child)
        if not lesson_info:
            return ret

        q = queue.Queue()
        q.put(lesson_info)
        lesson_ids = []
        lesson_outline_map = {}
        outline_block_map = {}
        while not q.empty():
            item: HistoryItem = q.get()
            if item.type == "outline":
                lesson_ids.append(item.bid)
            if item.children:
                if item.children[0].type == "outline":
                    for child in item.children:
                        q.put(child)
                else:
                    lesson_outline_map[item.bid] = [
                        block.bid for block in item.children
                    ]
                    outline_block_map[item.bid] = [block.bid for block in item.children]

        if not lesson_ids:
            return ret
        attend_infos = (
            LearnProgressRecord.query.filter(
                LearnProgressRecord.user_bid == user_id,
                LearnProgressRecord.outline_item_bid.in_(lesson_ids),
                LearnProgressRecord.shifu_bid == shifu_info.bid,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
            )
            .order_by(LearnProgressRecord.id)
            .all()
        )
        if not attend_infos:
            return ret
        attend_scripts: list[LearnGeneratedBlock] = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.outline_item_bid.in_(lesson_ids),
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.user_bid == user_id,
            )
            .order_by(LearnGeneratedBlock.id.asc())
            .all()
        )

        if len(attend_scripts) == 0:
            return ret
        items = [
            StudyRecordItemDTO(
                i.position,
                ROLE_VALUES[i.role],
                0,
                i.generated_content,
                i.block_bid,
                i.outline_item_bid if i.outline_item_bid in lesson_ids else lesson_id,
                i.generated_block_bid,
                i.liked,
                ui=json.loads(i.block_content_conf) if i.block_content_conf else None,
            )
            for i in attend_scripts
        ]
        user_info = load_user_aggregate(user_id)
        if not user_info:
            raise_error("USER.USER_NOT_FOUND")
        ret.records = items
        last_block_id = attend_scripts[-1].block_bid
        last_lesson_id = attend_scripts[-1].outline_item_bid
        last_attend: LearnProgressRecord = [
            atend for atend in attend_infos if atend.outline_item_bid == last_lesson_id
        ][-1]
        last_outline_item = get_outline_item_dto(app, last_lesson_id, preview_mode)
        if (
            last_lesson_id in lesson_outline_map
            and len(lesson_outline_map.get(last_lesson_id, []))
            > last_attend.block_position
        ):
            last_block_id = lesson_outline_map.get(last_lesson_id, [])[
                last_attend.block_position
            ]
        last_block = (
            block_model.query.filter(
                block_model.outline_item_bid == last_lesson_id,
                block_model.deleted == 0,
                block_model.block_bid == last_block_id,
            )
            .order_by(block_model.id.desc())
            .first()
        )
        if not last_block:
            ret.ui = []
            return ret
        block_dto: BlockDTO = generate_block_dto_from_model_internal(
            last_block, convert_html=False
        )

        uis = handle_ui(
            app,
            user_info,
            last_attend,
            last_outline_item,
            block_dto,
            "",
            MockClient(),
            {},
        )
        if len(uis) > 0:
            ret.ui = uis[0]
        lesson_id = last_lesson_id

        if (
            attend_scripts[-1].block_bid == last_block.block_bid
            and block_dto.type == BLOCK_TYPE_CONTENT
        ):
            ret.ui = _handle_output_continue(
                app,
                user_info,
                last_attend.progress_record_bid,
                last_outline_item,
                block_dto,
                {},
                MockClient(),
            )
        if len(uis) > 1:
            ret.ask_mode = uis[1].script_content.get("ask_mode", False)
            ret.ask_ui = uis[1]
        return ret


# get script info
@extensible
def get_script_info(
    app: Flask, user_id: str, script_id: str, preview_mode: bool = False
) -> ScriptInfoDTO:
    """
    Get the script info
    """
    with app.app_context():
        block_info = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == script_id,
            LearnGeneratedBlock.user_bid == user_id,
        ).first()
        if not block_info:
            return None
        outline_item: ShifuOutlineItemDto = get_outline_item_dto(
            app, block_info.outline_item_bid, preview_mode
        )
        if not outline_item:
            return None
        return ScriptInfoDTO(
            block_info.position,
            outline_item.title,
            outline_item.type == LESSON_TYPE_TRIAL,
        )


@extensible
def set_script_content_operation(
    app: Flask, user_id: str, log_id: str, interaction_type: int
):
    with app.app_context():
        script_info = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == log_id,
            LearnGeneratedBlock.user_bid == user_id,
        ).first()
        if not script_info:
            return None
        # update the script_info
        script_info.interaction_type = interaction_type
        db.session.merge(script_info)
        db.session.commit()
        return True
