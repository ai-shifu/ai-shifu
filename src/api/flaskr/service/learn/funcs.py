from flask import Flask
from typing import Union
from flaskr.dao import run_with_redis
from flaskr.framework.plugin.plugin_manager import extensible
from flaskr.service.learn.const import (
    ROLE_VALUES,
)
from ...service.learn.dtos import AILessonAttendDTO, StudyRecordDTO
import json
from ...service.order.consts import (
    LEARN_STATUS_LOCKED,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_RESET,
    get_learn_status_values,
    ORDER_STATUS_SUCCESS,
    LEARN_STATUS_NOT_EXIST,
)

from .dtos import AICourseDTO, StudyRecordItemDTO, ScriptInfoDTO
from ...service.lesson.const import (
    LESSON_TYPE_TRIAL,
)
from ...dao import db

from flaskr.service.learn.models import (
    LearnProgressRecord,
    LearnGeneratedBlock,
)
from .plugin import handle_ui
from flaskr.api.langfuse import MockClient
from flaskr.util.uuid import generate_id
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import (
    get_shifu_outline_tree,
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
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.service.learn.output.handle_output_continue import _handle_output_continue
from flaskr.service.order.models import Order


# fill the attend info for the outline items


def fill_attend_info(
    app: Flask, user_id: str, is_paid: bool, ret: AICourseDTO
) -> AICourseDTO:
    """
    Fill the attend info for the outline items
    Args:
        app: Flask application instance
        user_id: User id
        is_paid: Is paid
        ret: AICourseDTO
    Returns:
        AICourseDTO
    """
    attend_status_values = get_learn_status_values()
    q = queue.Queue()
    for lesson in ret.lessons:
        q.put(lesson)
    first_trial_lesson = False
    first_lessons = list[AILessonAttendDTO]()
    has_trial_init = False
    # has_normal_init = False

    while not q.empty():
        lesson: AILessonAttendDTO = q.get()
        if lesson.status_value == LEARN_STATUS_NOT_EXIST:
            # lesson_trial
            if lesson.lesson_type == LESSON_TYPE_TRIAL:
                if not has_trial_init:
                    if not first_trial_lesson and not lesson.parent:
                        first_trial_lesson = True
                        app.logger.info(f"first_trial_lesson: {lesson.lesson_id}")
                        app.logger.info(f"lesson: {lesson.__json__()}")
                        first_lessons.append(lesson)
                        lesson.status_value = LEARN_STATUS_NOT_STARTED
                        lesson.status = attend_status_values[LEARN_STATUS_NOT_STARTED]
                        lesson.updated = True
                    elif (
                        first_trial_lesson
                        and first_lessons[-1].children
                        and len(first_lessons[-1].children) > 0
                        and first_lessons[-1].children[0] == lesson
                    ):
                        lesson.status_value = LEARN_STATUS_NOT_STARTED
                        lesson.status = attend_status_values[LEARN_STATUS_NOT_STARTED]
                        lesson.updated = True
                        first_lessons.append(lesson)
                        if not lesson.children or len(lesson.children) == 0:
                            has_trial_init = True

            else:
                lesson.status_value = LEARN_STATUS_LOCKED
                lesson.status = attend_status_values[LEARN_STATUS_LOCKED]
                lesson.updated = True
        else:
            if lesson.lesson_type == LESSON_TYPE_TRIAL:
                has_trial_init = True

        if lesson.children:
            for child in lesson.children:
                q.put(child)

    for lesson in first_lessons:
        attend_info: LearnProgressRecord = LearnProgressRecord(
            user_bid=user_id,
            shifu_bid=ret.course_id,
            outline_item_bid=lesson.lesson_id,
            status=LEARN_STATUS_NOT_STARTED,
            outline_item_updated=0,
            progress_record_bid=generate_id(app),
        )
        db.session.add(attend_info)
    if len(first_lessons) > 0:
        db.session.commit()
    return ret


def get_lesson_tree_to_study_inner(
    app: Flask, user_id: str, course_id: str = None, preview_mode: bool = False
) -> AICourseDTO:
    """
    Get the lesson tree to study
    Args:
        app: Flask application instance
        user_id: User id
        course_id: Course id
        preview_mode: Preview mode
    Returns:
        AICourseDTO
    """
    with app.app_context():
        shifu_info: ShifuInfoDto = get_shifu_outline_tree(app, course_id, preview_mode)
        q = queue.Queue()
        for outline_item in shifu_info.outline_items:
            q.put(outline_item)
        outline_ids = []
        while not q.empty():
            item: ShifuOutlineItemDto = q.get()
            outline_ids.append(item.bid)
            if item.children:
                for child in item.children:
                    q.put(child)

        is_paid = preview_mode or shifu_info.price == 0
        if not is_paid:
            buy_record = Order.query.filter_by(
                user_bid=user_id, shifu_bid=course_id
            ).first()
            if buy_record:
                is_paid = buy_record.status == ORDER_STATUS_SUCCESS
        ret: AICourseDTO = AICourseDTO(
            course_id=course_id,
            course_name=shifu_info.title,
            teacher_avatar=shifu_info.avatar,
            course_price=shifu_info.price,
            lessons=[],
        )

        attend_infos = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_id,
            LearnProgressRecord.shifu_bid == course_id,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.outline_item_bid.in_(outline_ids),
        ).all()
        attend_map: dict[str, LearnProgressRecord] = {
            i.outline_item_bid: i for i in attend_infos
        }
        attend_status_values = get_learn_status_values()

        def recurse_outline_item(item: ShifuOutlineItemDto) -> AILessonAttendDTO:
            attend_info = attend_map.get(item.bid, None)
            ret = AILessonAttendDTO(
                lesson_id=item.bid,
                lesson_name=item.title,
                lesson_no=item.position,
                status_value=LEARN_STATUS_NOT_EXIST,
                status=attend_status_values[LEARN_STATUS_NOT_EXIST],
                lesson_type=item.type,
                children=[],
                unique_id=item.bid,
                updated=False,
            )
            if attend_info:
                ret.status_value = attend_info.status
                ret.status = attend_status_values[attend_info.status]
            if item.children:
                for child in item.children:
                    child_ret = recurse_outline_item(child)
                    child_ret.parent = ret
                    ret.children.append(child_ret)
            return ret

        ret.lessons = [recurse_outline_item(i) for i in shifu_info.outline_items]
        ret = fill_attend_info(app, user_id, is_paid, ret)
        return ret


@extensible
def get_lesson_tree_to_study(
    app: Flask, user_id: str, course_id: str = None, preview_mode: bool = False
) -> AICourseDTO:
    """
    Get the lesson tree to study
    the lesson tree is used to display the lesson tree in the client
    Args:
        app: Flask application instance
        user_id: User id
        course_id: Course id
        preview_mode: Preview mode
    Returns:
        AICourseDTO
    """
    return run_with_redis(
        app,
        app.config.get("REDIS_KEY_PREFIX") + ":get_lesson_tree_to_study:" + user_id,
        5,
        get_lesson_tree_to_study_inner,
        [app, user_id, course_id, preview_mode],
    )


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
        user_info = User.query.filter_by(user_id=user_id).first()
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
        block_model: Union[DraftBlock, PublishedBlock] = (
            DraftBlock if preview_mode else PublishedBlock
        )
        block_info = block_model.query.filter(
            block_model.block_bid == script_id,
            block_model.deleted == 0,
        ).first()
        if not block_info:
            return None
        outline_item: ShifuOutlineItemDto = get_outline_item_dto(
            app, block_info.outline_item_bid, preview_mode
        )
        if not outline_item:
            return None
        return ScriptInfoDTO(
            block_info.position - 1,
            outline_item.title,
            outline_item.type == LESSON_TYPE_TRIAL,
        )


# reset user study info by lesson
@extensible
def reset_user_study_info_by_lesson(
    app: Flask, user_id: str, lesson_id: str, preview_mode: bool = False
):
    with app.app_context():
        app.logger.info(
            f"reset_user_study_info_by_lesson {lesson_id},preview_mode: {preview_mode}"
        )

        outline_item: ShifuOutlineItemDto = get_outline_item_dto(
            app, lesson_id, preview_mode
        )
        if not outline_item:
            app.logger.info("lesson_info not found")
            return False
        struct: HistoryItem = get_shifu_struct(
            app, outline_item.shifu_bid, preview_mode
        )

        current_path = find_node_with_parents(struct, outline_item.bid)
        lesson_ids = set()
        if not current_path or len(current_path) < 2:
            app.logger.info("current_path not found")
            return False
        root_outline_item: HistoryItem = current_path[1]
        q = queue.Queue()
        q.put(root_outline_item)
        first_lesson_ids = []
        while not q.empty():
            item: HistoryItem = q.get()
            if item.type == "outline":
                lesson_ids.add(item.bid)

            if item.children and item.children[0].type == "outline":
                for child in item.children:
                    q.put(child)

        first_lesson_ids = set()
        first_lesson_ids.add(root_outline_item.bid)
        top = root_outline_item
        while top.children and top.children[0].type == "outline":
            first_lesson_ids.add(top.children[0].bid)
            top = top.children[0]
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_id,
            LearnProgressRecord.outline_item_bid.in_(lesson_ids),
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.shifu_bid == struct.bid,
        ).update({"status": LEARN_STATUS_RESET})

        # insert the new attend info for the lessons that are available
        for lesson in lesson_ids:
            attend_info = LearnProgressRecord(
                user_bid=user_id,
                outline_item_bid=lesson,
                shifu_bid=struct.bid,
                status=LEARN_STATUS_LOCKED,
                outline_item_updated=0,
            )
            attend_info.progress_record_bid = generate_id(app)
            if lesson in first_lesson_ids:
                attend_info.status = LEARN_STATUS_IN_PROGRESS
            else:
                attend_info.status = LEARN_STATUS_LOCKED
            db.session.add(attend_info)
        LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.outline_item_bid.in_(lesson_ids),
            LearnGeneratedBlock.status == 1,
            LearnGeneratedBlock.user_bid == user_id,
        ).update({"status": 0})
        db.session.commit()
        return True


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
