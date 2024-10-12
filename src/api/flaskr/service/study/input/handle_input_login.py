from trace import Trace
from flask import Flask
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_REQUIRE_LOGIN
from flaskr.service.study.plugin import register_input_handler
from flaskr.service.study.utils import make_script_dto


@register_input_handler(input_type=INPUT_TYPE_REQUIRE_LOGIN)
def handle_input_login(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    # todo
    yield make_script_dto(
        INPUT_TYPE_REQUIRE_LOGIN,
        script_info.script_ui_content,
        script_info.script_id,
    )
