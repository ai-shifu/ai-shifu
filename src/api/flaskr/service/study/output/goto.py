from flask import Flask

from sqlalchemy import func

from flaskr.service.order.consts import (
    ATTEND_STATUS_BRANCH,
    ATTEND_STATUS_IN_PROGRESS,
    ATTEND_STATUS_RESET,
)
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.plugin import register_shifu_output_handler
from flaskr.service.study.models import AICourseAttendAsssotion
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.lesson.models import AILesson
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.study.const import INPUT_TYPE_BRANCH
from flaskr.dao import db
from flaskr.service.user.models import User
from flaskr.util.uuid import generate_id
from flaskr.service.study.utils import get_script_ui_label
from flaskr.i18n import _
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from flaskr.service.shifu.dtos import GotoDTO
from langfuse.client import StatefulTraceClient


@register_shifu_output_handler("goto")
def _handle_output_goto(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
) -> ScriptDTO:
    app.logger.info("branch")
    goto: GotoDTO = block_dto.block_content
    branch_info = goto.conditions
    branch_key = branch_info.get("var_name", "")
    profile = get_user_profiles(
        app, user_info.user_id, outline_item_info.shifu_bid, [branch_key]
    )
    branch_value = profile.get(branch_key, "") if profile else ""
    jump_rule = branch_info.get("jump_rule", [])
    app.logger.info("rule:{}".format(jump_rule))
    course_id = outline_item_info.shifu_bid
    for rule in jump_rule:
        app.logger.info(
            "branch value:'{}' rule:'{}'".format(branch_value, rule.get("value", ""))
        )
        if branch_value == rule.get("value", ""):
            app.logger.info("branch jump begin")

            attend_info = AICourseLessonAttend.query.filter(
                AICourseLessonAttend.attend_id == attend_id
            ).first()
            next_lesson = None
            if rule.get("lark_table_id", "") != "":
                next_lesson = AILesson.query.filter(
                    AILesson.lesson_feishu_id == rule.get("lark_table_id", ""),
                    AILesson.status == 1,
                    AILesson.course_id == course_id,
                    func.length(AILesson.lesson_no) > 2,
                ).first()
            if rule.get("goto_id", "") != "":
                next_lesson = AILesson.query.filter(
                    AILesson.lesson_id == rule.get("goto_id", ""),
                    AILesson.status == 1,
                    AILesson.course_id == course_id,
                ).first()
            if next_lesson:
                next_attend = AICourseLessonAttend.query.filter(
                    AICourseLessonAttend.user_id == user_info.user_id,
                    AICourseLessonAttend.course_id == course_id,
                    AICourseLessonAttend.lesson_id == next_lesson.lesson_id,
                    AICourseLessonAttend.status != ATTEND_STATUS_RESET,
                ).first()
                if next_attend is None:
                    next_attend = AICourseLessonAttend()
                    next_attend.user_id = user_info.user_id
                    next_attend.course_id = next_lesson.course_id
                    next_attend.lesson_id = next_lesson.lesson_id
                    next_attend.attend_id = generate_id(app)
                    next_attend.lesson_no = next_lesson.lesson_no
                    db.session.add(next_attend)
                assoation = AICourseAttendAsssotion()
                assoation.from_attend_id = attend_info.attend_id
                assoation.to_attend_id = next_attend.attend_id
                assoation.user_id = user_info.user_id
                db.session.add(assoation)
                next_attend.status = ATTEND_STATUS_IN_PROGRESS
                next_attend.script_index = 0
                attend_info.status = ATTEND_STATUS_BRANCH
                db.session.flush()
                attend_info = next_attend
                app.logger.info(
                    "branch jump to lesson:{}".format(next_lesson.lesson_no)
                )
            else:
                app.logger.warning(
                    "next lesson is not found,lark_table_id:{}".format(
                        rule.get("lark_table_id", "")
                    )
                )
            break
    else:
        app.logger.warning(
            "branch value is not found,branch_value:{} rule:{}".format(
                branch_value, jump_rule
            )
        )
        msg = get_script_ui_label(app, block_dto.block_content)
    if not msg:
        msg = _("COMMON.CONTINUE")
    btn = [
        {
            "label": msg,
            "value": block_dto.block_content,
            "type": INPUT_TYPE_BRANCH,
        }
    ]
    return ScriptDTO(
        "buttons",
        {"buttons": btn},
        outline_item_info.bid,
        outline_item_info.bid,
    )
