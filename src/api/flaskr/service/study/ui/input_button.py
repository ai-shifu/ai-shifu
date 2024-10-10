from flask import Flask

from flaskr.service.lesson.const import UI_TYPE_BUTTON
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.study.utils import make_script_dto
from flaskr.service.study.const import INPUT_TYPE_CONTINUE


@register_ui_handler(UI_TYPE_BUTTON)
def handle_input_button(
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
            "type": INPUT_TYPE_CONTINUE,
        }
    ]
    yield make_script_dto(
        "buttons", {"title": "接下来", "buttons": btn}, script_info.script_id
    )
