from flask import Flask
from typing import Union
from flaskr.dao import run_with_redis
from flaskr.framework.plugin.plugin_manager import extensible
from flaskr.service.study.const import (
    ROLE_VALUES,
)
from ...service.study.dtos import AILessonAttendDTO, StudyRecordDTO
import json
from ...service.order.consts import (
    ATTEND_STATUS_BRANCH,
    ATTEND_STATUS_LOCKED,
    ATTEND_STATUS_NOT_STARTED,
    ATTEND_STATUS_IN_PROGRESS,
    ATTEND_STATUS_RESET,
    get_attend_status_values,
    BUY_STATUS_SUCCESS,
    ATTEND_STATUS_NOT_EXIST,
)

from .dtos import AICourseDTO, StudyRecordItemDTO, StudyRecordProgressDTO, ScriptInfoDTO
from ...service.lesson.const import (
    LESSON_TYPE_TRIAL,
    STATUS_PUBLISH,
    STATUS_DRAFT,
)
from ...dao import db

from ...service.lesson.models import AILesson, AILessonScript
from ...service.order.models import (
    AICourseBuyRecord,
    AICourseLessonAttend,
)
from .models import AICourseLessonAttendScript, AICourseAttendAsssotion
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
    ShifuDraftBlock,
    ShifuPublishedBlock,
)
from flaskr.service.shifu.adapter import (
    BlockDTO,
    generate_block_dto_from_model_internal,
)
from flaskr.service.shifu.consts import BLOCK_TYPE_CONTENT
import queue
from flaskr.service.shifu.struct_uils import find_node_with_parents
from flaskr.service.study.output.handle_output_continue import _handle_output_continue


from flaskr.service.study.plugin import check_block_continue


# fill the attend info for the outline items


def fill_attend_info(
    app: Flask, user_id: str, is_paid: bool, ret: AICourseDTO
) -> AICourseDTO:
    attend_status_values = get_attend_status_values()
    q = queue.Queue()
    for lesson in ret.lessons:
        q.put(lesson)
    first_trial_lesson = False
    first_lessons = list[AILessonAttendDTO]()
    has_trial_init = False
    # has_normal_init = False

    while not q.empty():
        lesson: AILessonAttendDTO = q.get()
        if lesson.status_value == ATTEND_STATUS_NOT_EXIST:
            # lesson_trial
            if lesson.lesson_type == LESSON_TYPE_TRIAL:
                if not has_trial_init:
                    if not first_trial_lesson and not lesson.parent:
                        first_trial_lesson = True
                        app.logger.info(f"first_trial_lesson: {lesson.lesson_id}")
                        app.logger.info(f"lesson: {lesson.__json__()}")
                        first_lessons.append(lesson)
                        lesson.status_value = ATTEND_STATUS_NOT_STARTED
                        lesson.status = attend_status_values[ATTEND_STATUS_NOT_STARTED]
                        lesson.updated = True
                    elif (
                        first_trial_lesson
                        and first_lessons[-1].children
                        and len(first_lessons[-1].children) > 0
                        and first_lessons[-1].children[0] == lesson
                    ):
                        lesson.status_value = ATTEND_STATUS_NOT_STARTED
                        lesson.status = attend_status_values[ATTEND_STATUS_NOT_STARTED]
                        lesson.updated = True
                        first_lessons.append(lesson)
                        if not lesson.children or len(lesson.children) == 0:
                            has_trial_init = True

            else:
                lesson.status_value = ATTEND_STATUS_LOCKED
                lesson.status = attend_status_values[ATTEND_STATUS_LOCKED]
                lesson.updated = True
        else:
            if lesson.lesson_type == LESSON_TYPE_TRIAL:
                has_trial_init = True

        if lesson.children:
            for child in lesson.children:
                q.put(child)

    for lesson in first_lessons:
        attend_info: AICourseLessonAttend = AICourseLessonAttend(
            user_id=user_id,
            course_id=ret.course_id,
            lesson_id=lesson.lesson_id,
            status=ATTEND_STATUS_NOT_STARTED,
            script_index=0,
            attend_id=generate_id(app),
        )
        db.session.add(attend_info)
    if len(first_lessons) > 0:
        db.session.commit()
    return ret


def get_lesson_tree_to_study_inner(
    app: Flask, user_id: str, course_id: str = None, preview_mode: bool = False
) -> AICourseDTO:
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
            buy_record = AICourseBuyRecord.query.filter_by(
                user_id=user_id, course_id=course_id
            ).first()
            if buy_record:
                is_paid = buy_record.status == BUY_STATUS_SUCCESS
        ret: AICourseDTO = AICourseDTO(
            course_id=course_id,
            course_name=shifu_info.title,
            teacher_avatar=shifu_info.avatar,
            course_price=shifu_info.price,
            lessons=[],
        )

        attend_infos = AICourseLessonAttend.query.filter(
            AICourseLessonAttend.user_id == user_id,
            AICourseLessonAttend.course_id == course_id,
            AICourseLessonAttend.status != ATTEND_STATUS_RESET,
            AICourseLessonAttend.lesson_id.in_(outline_ids),
        ).all()
        attend_map = {i.lesson_id: i for i in attend_infos}
        attend_status_values = get_attend_status_values()

        def recurse_outline_item(item: ShifuOutlineItemDto) -> AILessonAttendDTO:
            attend_info = attend_map.get(item.bid, None)
            ret = AILessonAttendDTO(
                lesson_id=item.bid,
                lesson_name=item.title,
                lesson_no=item.position,
                status_value=ATTEND_STATUS_NOT_EXIST,
                status=attend_status_values[ATTEND_STATUS_NOT_EXIST],
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
    with app.app_context():
        block_model: Union[ShifuDraftBlock, ShifuPublishedBlock] = (
            ShifuDraftBlock if preview_mode else ShifuPublishedBlock
        )
        outline_item: ShifuOutlineItemDto = get_outline_item_dto(
            app, lesson_id, preview_mode
        )
        if not outline_item:
            return None
        shifu_info: ShifuInfoDto = get_shifu_dto(
            app, outline_item.shifu_bid, preview_mode
        )
        if not shifu_info:
            return None
        teacher_avatar = shifu_info.avatar

        shifu_struct: HistoryItem = get_shifu_struct(
            app, outline_item.shifu_bid, preview_mode
        )
        if not shifu_struct:
            return None

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
            return None

        q = queue.Queue()
        q.put(lesson_info)
        lesson_ids = []
        lesson_outline_map = {}
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

        if not lesson_ids:
            return None

        attend_infos = (
            AICourseLessonAttend.query.filter(
                AICourseLessonAttend.user_id == user_id,
                AICourseLessonAttend.lesson_id.in_(lesson_ids),
                AICourseLessonAttend.course_id == shifu_info.bid,
                AICourseLessonAttend.status != ATTEND_STATUS_RESET,
            )
            .order_by(AICourseLessonAttend.id)
            .all()
        )
        if not attend_infos:
            return None
        attend_ids = [attend_info.attend_id for attend_info in attend_infos]
        attend_scripts = (
            AICourseLessonAttendScript.query.filter(
                AICourseLessonAttendScript.attend_id.in_(attend_ids),
                AICourseLessonAttendScript.status == 1,
            )
            .order_by(AICourseLessonAttendScript.id.asc())
            .all()
        )

        def get_script_index(x: AICourseLessonAttendScript):
            lesson_index = lesson_ids.index(x.lesson_id)
            if x.lesson_id in lesson_outline_map:
                return (
                    lesson_index * 10000
                    + lesson_outline_map.get(
                        x.lesson_id,
                    ).index(x.script_id)
                    * 100
                )
            else:
                return lesson_index * 10000 + 10000

        attend_scripts.sort(key=get_script_index)
        if len(attend_scripts) == 0:
            return StudyRecordDTO([])
        items = [
            StudyRecordItemDTO(
                i.script_index,
                ROLE_VALUES[i.script_role],
                0,
                i.script_content,
                i.script_id,
                i.lesson_id if i.lesson_id in lesson_ids else lesson_id,
                i.log_id,
                i.interaction_type,
                ui=json.loads(i.script_ui_conf) if i.script_ui_conf else None,
            )
            for i in attend_scripts
        ]
        user_info = User.query.filter_by(user_id=user_id).first()
        ret = StudyRecordDTO(items, teacher_avatar=teacher_avatar)
        last_block_id = attend_scripts[-1].script_id
        last_block: Union[ShifuDraftBlock, ShifuPublishedBlock] = (
            block_model.query.filter(
                block_model.block_bid == last_block_id, block_model.deleted == 0
            )
            .order_by(block_model.id.desc())
            .first()
        )
        if not last_block:
            ret.ui = []
            return ret
        block_dto: BlockDTO = generate_block_dto_from_model_internal(last_block)
        next_block_id = last_block.id
        last_lesson_id = last_block.outline_item_bid

        if block_dto.type == BLOCK_TYPE_CONTENT:
            # if the block is content, we need to find the next block
            q = queue.Queue()
            q.put(lesson_info)
            while not q.empty():
                item: HistoryItem = q.get()
                if (
                    item.type == "outline"
                    and item.children
                    and item.children[0].type == "block"
                    and block_dto.bid in [i.bid for i in item.children]
                ):
                    index = [i.bid for i in item.children].index(block_dto.bid)
                    if index < len(item.children) - 1:
                        next_block_id = item.children[index + 1].id
                        last_lesson_id = item.bid
                        break
                if item.children:
                    for child in item.children:
                        q.put(child)

        if next_block_id and next_block_id != last_block.id:
            last_block: Union[ShifuDraftBlock, ShifuPublishedBlock] = (
                block_model.query.filter(block_model.id == next_block_id).first()
            )
            block_dto: BlockDTO = generate_block_dto_from_model_internal(last_block)
            last_lesson_id = last_block.outline_item_bid

        lesson_id = last_lesson_id
        last_attends = [i for i in attend_infos if i.lesson_id == last_lesson_id]
        if len(last_attends) == 0:
            last_attend = (
                AICourseLessonAttend.query.filter(
                    AICourseLessonAttend.user_id == user_id,
                    AICourseLessonAttend.lesson_id == last_lesson_id,
                    AICourseLessonAttend.status != ATTEND_STATUS_RESET,
                )
                .order_by(AICourseLessonAttend.id.desc())
                .first()
            )
            if last_attend is None:
                pass
        else:
            last_attend = last_attends[-1]
        last_outline_item: ShifuOutlineItemDto = get_outline_item_dto(
            app, last_lesson_id, preview_mode
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
        app.logger.info(
            "uis:{}".format(json.dumps([i.__json__() for i in uis], ensure_ascii=False))
        )
        if len(uis) > 0:
            ret.ui = uis[0]
        if check_block_continue(
            app,
            user_info,
            last_attend.attend_id,
            last_outline_item,
            block_dto,
            {},
            MockClient(),
        ):
            ret.ui = _handle_output_continue(
                app,
                user_info,
                last_attend.attend_id,
                last_outline_item,
                block_dto,
                {},
                MockClient(),
            )
        if len(uis) > 1:
            ret.ask_mode = uis[1].script_content.get("ask_mode", False)
            ret.ask_ui = uis[1]
        return ret


@extensible
def get_lesson_study_progress(
    app: Flask, user_id: str, lesson_id: str
) -> StudyRecordProgressDTO:
    with app.app_context():
        attend_status_values = get_attend_status_values()
        lesson_info = (
            AILesson.query.filter(
                AILesson.lesson_id == lesson_id,
                AILesson.status == 1,
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        if not lesson_info:
            return None
        attend_info = (
            AICourseLessonAttend.query.filter(
                AICourseLessonAttend.user_id == user_id,
                AICourseLessonAttend.lesson_id == lesson_id,
                AICourseLessonAttend.status != ATTEND_STATUS_RESET,
            )
            .order_by(AICourseLessonAttend.id.desc())
            .first()
        )
        if not attend_info:
            return None

        lesson_no = lesson_info.lesson_no
        lesson_name = lesson_info.lesson_name
        script_index = 0
        script_name = ""
        is_branch = False
        while attend_info is not None and attend_info.status == ATTEND_STATUS_BRANCH:
            script_index = script_index + attend_info.script_index
            is_branch = True
            associaions = AICourseAttendAsssotion.query.filter_by(
                user_id=user_id, from_attend_id=attend_info.attend_id
            ).first()
            if associaions:
                attend_info = AICourseLessonAttend.query.filter_by(
                    attend_id=associaions.to_attend_id
                ).first()

        if attend_info is None:
            return None

        script_info = (
            AILessonScript.query.filter(
                AILessonScript.lesson_id == attend_info.lesson_id,
                AILessonScript.script_index == attend_info.script_index,
                AILessonScript.status == 1,
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
        if script_info is None:
            return None

        script_name = script_info.script_name
        return StudyRecordProgressDTO(
            lesson_id,
            lesson_name,
            lesson_no,
            attend_status_values[attend_info.status],
            script_index,
            script_name,
            is_branch,
        )


# get script info
@extensible
def get_script_info(
    app: Flask, user_id: str, script_id: str, preview_mode: bool = False
) -> ScriptInfoDTO:
    with app.app_context():
        ai_course_status = [STATUS_PUBLISH]
        if preview_mode:
            ai_course_status = [STATUS_DRAFT]
        script_info = (
            AILessonScript.query.filter(
                AILessonScript.script_id == script_id,
                AILessonScript.status.in_(ai_course_status),
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
        if not script_info:
            return None
        lesson = (
            AILesson.query.filter(
                AILesson.lesson_id == script_info.lesson_id,
                AILesson.status.in_(ai_course_status),
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        if not lesson:
            return None
        return ScriptInfoDTO(
            script_info.script_index,
            script_info.script_name,
            lesson.lesson_type == LESSON_TYPE_TRIAL,
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
        AICourseLessonAttend.query.filter(
            AICourseLessonAttend.user_id == user_id,
            AICourseLessonAttend.lesson_id.in_(lesson_ids),
            AICourseLessonAttend.status != ATTEND_STATUS_RESET,
            AICourseLessonAttend.course_id == struct.bid,
        ).update({"status": ATTEND_STATUS_RESET})

        # insert the new attend info for the lessons that are available
        for lesson in lesson_ids:
            attend_info = AICourseLessonAttend(
                user_id=user_id,
                lesson_id=lesson,
                course_id=struct.bid,
                status=ATTEND_STATUS_LOCKED,
                script_index=0,
            )
            attend_info.attend_id = generate_id(app)
            if lesson in first_lesson_ids:
                attend_info.status = ATTEND_STATUS_IN_PROGRESS
            else:
                attend_info.status = ATTEND_STATUS_LOCKED
            db.session.add(attend_info)
        db.session.commit()
        return True


@extensible
def set_script_content_operation(
    app: Flask, user_id: str, log_id: str, interaction_type: int
):
    with app.app_context():
        script_info = AICourseLessonAttendScript.query.filter(
            AICourseLessonAttendScript.log_id == log_id,
            AICourseLessonAttendScript.user_id == user_id,
        ).first()
        if not script_info:
            return None
        # update the script_info
        script_info.interaction_type = interaction_type
        db.session.merge(script_info)
        db.session.commit()
        return True
