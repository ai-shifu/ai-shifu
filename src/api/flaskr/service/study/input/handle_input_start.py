from flask import Flask
from flaskr.service.lesson.models import AILessonScript, AILesson
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_START
from flaskr.service.study.plugin import register_input_handler
from trace import Trace
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.user.models import User


@register_input_handler(input_type=INPUT_TYPE_START)
@extensible_generic
def handle_input_start(
    app: Flask,
    user_info: User,
    lesson: AILesson,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):

    return None
