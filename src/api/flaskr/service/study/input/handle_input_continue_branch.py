import json
from trace import Trace
from flask import Flask
from sqlalchemy import func
from flaskr.service.lesson.const import UI_TYPE_BRANCH
from flaskr.service.lesson.models import AILesson, AILessonScript
from flaskr.service.order.consts import (
    ATTEND_STATUS_BRANCH,
    ATTEND_STATUS_IN_PROGRESS,
    ATTEND_STATUS_RESET,
)
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.study.models import AICourseAttendAsssotion
from flaskr.service.study.plugin import register_continue_handler
from flaskr.util.uuid import generate_id
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.user.models import User


@register_continue_handler(script_ui_type=UI_TYPE_BRANCH)
@extensible_generic
def handle_input_continue_branch(
    app: Flask,
    user_info: User,
    lesson_info: AILesson,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    app.logger.info(
        "script_id:{},branch:{}".format(
            script_info.script_id, script_info.script_other_conf
        )
    )
    branch_info = json.loads(script_info.script_other_conf)
    branch_key = branch_info.get("var_name", "")
    profile = get_user_profiles(app, user_info.user_id, attend.course_id, [branch_key])
    branch_value = profile.get(branch_key, "")
    jump_rule = branch_info.get("jump_rule", [])

    app.logger.info("branch key:{}".format(branch_key))
    if attend.status != ATTEND_STATUS_BRANCH:
        for rule in jump_rule:
            app.logger.info(
                "rule value:'{}' branch_value:'{}'".format(
                    rule.get("value", ""), branch_value
                )
            )
            if branch_value == rule.get("value", ""):
                app.logger.info("found branch rule")
                attend_info = AICourseLessonAttend.query.filter(
                    AICourseLessonAttend.attend_id == attend.attend_id
                ).first()
                next_lesson = None
                if rule.get("lark_table_id", "") != "":
                    next_lesson = AILesson.query.filter(
                        AILesson.lesson_feishu_id == rule.get("lark_table_id", ""),
                        AILesson.status == 1,
                        AILesson.course_id == attend.course_id,
                        func.length(AILesson.lesson_no) > 2,
                    ).first()
                if rule.get("goto_id", "") != "":
                    next_lesson = AILesson.query.filter(
                        AILesson.lesson_id == rule.get("goto_id", ""),
                        AILesson.status == 1,
                        AILesson.course_id == attend.course_id,
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
