from flask import Flask
import json

from sqlalchemy import func

from flaskr.service.order.consts import ATTEND_STATUS_BRANCH, ATTEND_STATUS_IN_PROGRESS
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.study.utils import make_script_dto
from flaskr.service.study.const import INPUT_TYPE_BRANCH
from flaskr.service.study.models import AICourseAttendAsssotion
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.lesson.models import AILesson
from flaskr.service.lesson.const import UI_TYPE_BRANCH

from flaskr.dao import db


@register_ui_handler(UI_TYPE_BRANCH)
def handle_input_branch(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
):
    app.logger.info("branch")
    branch_info = json.loads(script_info.script_other_conf)
    branch_key = branch_info.get("var_name", "")
    profile = get_user_profiles(app, user_id, [branch_key])
    branch_value = profile.get(branch_key, "")
    jump_rule = branch_info.get("jump_rule", [])
    course_id = attend.course_id
    for rule in jump_rule:
        if branch_value == rule.get("value", ""):
            attend_info = AICourseLessonAttend.query.filter(
                AICourseLessonAttend.attend_id == attend.attend_id
            ).first()
            next_lesson = AILesson.query.filter(
                AILesson.lesson_feishu_id == rule.get("lark_table_id", ""),
                AILesson.status == 1,
                AILesson.course_id == course_id,
                func.length(AILesson.lesson_no) > 2,
            ).first()
            if next_lesson:
                next_attend = AICourseLessonAttend.query.filter(
                    AICourseLessonAttend.user_id == user_id,
                    AICourseLessonAttend.course_id == course_id,
                    AICourseLessonAttend.lesson_id == next_lesson.lesson_id,
                ).first()
                if next_attend:
                    assoation = AICourseAttendAsssotion()
                    assoation.from_attend_id = attend_info.attend_id
                    assoation.to_attend_id = next_attend.attend_id
                    assoation.user_id = user_id
                    db.session.add(assoation)
                    next_attend.status = ATTEND_STATUS_IN_PROGRESS
                    next_attend.script_index = 0
                    attend_info.status = ATTEND_STATUS_BRANCH
                    db.session.flush()
                    attend_info = next_attend

    btn = [
        {
            "label": script_info.script_ui_content,
            "value": script_info.script_ui_content,
            "type": INPUT_TYPE_BRANCH,
        }
    ]
    yield make_script_dto(
        "buttons", {"title": "接下来", "buttons": btn}, script_info.script_id
    )
