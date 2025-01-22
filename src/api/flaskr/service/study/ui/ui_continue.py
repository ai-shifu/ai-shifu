from flask import Flask

from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_CONTINUE
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.user.models import User
from flaskr.i18n import _


def make_continue_ui(
    app: Flask,
    user_info: User,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
) -> ScriptDTO:
    msg = script_info.script_ui_content
    if msg == "":
        msg = _("COMMON.CONTINUE")
    btn = [
        {
            "label": msg,
            "value": msg,
            "type": INPUT_TYPE_CONTINUE,
        }
    ]
    return ScriptDTO(
        "buttons",
        {"title": msg, "buttons": btn},
        script_info.lesson_id,
        script_info.script_id,
    )
