from flask import Flask
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_START
from flaskr.service.study.plugin import register_input_handler
from trace import Trace


@register_input_handler(input_type=INPUT_TYPE_START)
def handle_input_start(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):

    return None
