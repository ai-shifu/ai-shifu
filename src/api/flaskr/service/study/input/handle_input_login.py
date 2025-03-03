from trace import Trace
from flask import Flask
from flaskr.service.study.input_funcs import BreakException
from flaskr.service.user.models import User
from flaskr.service.lesson.models import AILessonScript, AILesson
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_LOGIN, ROLE_STUDENT
from flaskr.service.study.plugin import register_input_handler
from flaskr.service.study.utils import generation_attend, make_script_dto
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic


@register_input_handler(input_type=INPUT_TYPE_LOGIN)
@extensible_generic
def handle_input_login(
    app: Flask,
    user_info: User,
    lesson: AILesson,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT  # type: ignore
    db.session.add(log_script)
    if user_info.user_state != 0:
        yield make_script_dto("text", "", script_info.script_id, script_info.lesson_id)
    else:
        raise BreakException
