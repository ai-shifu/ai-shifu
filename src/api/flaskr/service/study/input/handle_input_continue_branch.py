from flask import Flask
from sqlalchemy import func
from flaskr.service.lesson.models import AILesson
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.order.consts import (
    ATTEND_STATUS_BRANCH,
    ATTEND_STATUS_IN_PROGRESS,
    ATTEND_STATUS_RESET,
)
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.study.models import AICourseAttendAsssotion
from flaskr.service.study.plugin import (
    register_shifu_continue_handler,
)
from flaskr.util.uuid import generate_id
from flaskr.dao import db
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from flaskr.service.shifu.dtos import GotoDTO
from langfuse.client import StatefulTraceClient


@register_shifu_continue_handler("goto")
def _handle_input_continue_branch(
    app: Flask,
    user_info: User,
    attend_id: str,
    input: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    goto: GotoDTO = block_dto.block_content
    branch_info = goto.conditions
    branch_key = block_dto.variable_bids[0]
    profile = get_user_profiles(
        app, user_info.user_id, outline_item_info.shifu_bid, [branch_key]
    )
    branch_value = profile.get(branch_key, "")
    jump_rule = branch_info[0].jump_rule
    attend_info = AICourseLessonAttend.query.filter(
        AICourseLessonAttend.attend_id == attend_id
    ).first()

    app.logger.info("branch key:{}".format(branch_key))
    if attend_info.status != ATTEND_STATUS_BRANCH:
        for rule in jump_rule:
            app.logger.info(
                "rule value:'{}' branch_value:'{}'".format(
                    rule.get("value", ""), branch_value
                )
            )
            if branch_value == rule.get("value", ""):
                app.logger.info("found branch rule")
                attend_info = AICourseLessonAttend.query.filter(
                    AICourseLessonAttend.attend_id == attend_id
                ).first()
                next_lesson = None
                if rule.get("lark_table_id", "") != "":
                    next_lesson = AILesson.query.filter(
                        AILesson.lesson_feishu_id == rule.get("lark_table_id", ""),
                        AILesson.status == 1,
                        AILesson.course_id == attend_info.course_id,
                        func.length(AILesson.lesson_no) > 2,
                    ).first()
                if rule.get("goto_id", "") != "":
                    next_lesson = AILesson.query.filter(
                        AILesson.lesson_id == rule.get("goto_id", ""),
                        AILesson.status == 1,
                        AILesson.course_id == attend_info.course_id,
                    ).first()
                if next_lesson:
                    next_attend = AICourseLessonAttend.query.filter(
                        AICourseLessonAttend.user_id == user_info.user_id,
                        AICourseLessonAttend.course_id == next_lesson.course_id,
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
                    if next_attend:
                        assoation = AICourseAttendAsssotion.query.filter(
                            AICourseAttendAsssotion.from_attend_id
                            == attend_info.attend_id,  # noqa: W503
                            AICourseAttendAsssotion.to_attend_id
                            == next_attend.attend_id,  # noqa: W503
                        ).first()
                        if not assoation:
                            assoation = AICourseAttendAsssotion()
                            assoation.from_attend_id = attend_info.attend_id
                            assoation.to_attend_id = next_attend.attend_id
                            assoation.user_id = user_info.user_id
                            db.session.add(assoation)
                        next_attend.status = ATTEND_STATUS_IN_PROGRESS
                        next_attend.script_index = -1
                        attend_info.status = ATTEND_STATUS_BRANCH
                        attend_info = next_attend
                        app.logger.info("branch jump")
                    break
                else:
                    app.logger.warning(
                        "branch lesson not found: {}".format(
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
    else:
        app.logger.warning("attend status is not branch")
