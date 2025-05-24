from flask import Flask

from flaskr.service.study.const import INPUT_TYPE_REQUIRE_LOGIN
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.lesson.const import (
    UI_TYPE_LOGIN,
)
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.user.models import User
from flaskr.i18n import _


@register_ui_handler(UI_TYPE_LOGIN)
def handle_require_login(
    app: Flask,
    user_info: User,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
) -> ScriptDTO:
    title = script_info.script_ui_content
    if not title:
        title = _("COMMON.LOGIN")
    btn = [
        {
            "label": title,
            "value": title,
            "type": INPUT_TYPE_REQUIRE_LOGIN,
        }
    ]
    return ScriptDTO(
        INPUT_TYPE_REQUIRE_LOGIN,
        {"buttons": btn},
        script_info.lesson_id,
        script_info.script_id,
    )
