from flask import Flask

from flaskr.service.lesson.const import UI_TYPE_PHONE
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_PHONE
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.study.utils import make_script_dto


@register_ui_handler(UI_TYPE_PHONE)
def handle_input_phone(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
):
    yield make_script_dto(
        INPUT_TYPE_PHONE, script_info.script_ui_content, script_info.script_id
    )
