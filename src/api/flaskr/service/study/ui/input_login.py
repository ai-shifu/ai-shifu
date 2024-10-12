from flask import Flask

from flaskr.service.study.const import INPUT_TYPE_REQUIRE_LOGIN
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.lesson.const import (
    UI_TYPE_LOGIN,
)
from flaskr.service.study.utils import make_script_dto


@register_ui_handler(UI_TYPE_LOGIN)
def handle_require_login(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
):

    btn = [
        {
            "label": script_info.script_ui_content,
            "value": script_info.script_ui_content,
            "type": INPUT_TYPE_REQUIRE_LOGIN,
        }
    ]
    yield make_script_dto(
        INPUT_TYPE_REQUIRE_LOGIN,
        {"title": "接下来", "buttons": btn},
        script_info.script_id,
    )
