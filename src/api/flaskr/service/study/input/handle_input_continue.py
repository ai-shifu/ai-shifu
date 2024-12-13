from trace import Trace
from flask import Flask
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_CONTINUE, ROLE_STUDENT
from flaskr.service.study.plugin import (
    register_input_handler,
    CONTINUE_HANDLE_MAP,
)
from flaskr.service.study.utils import generation_attend
from flaskr.dao import db


@register_input_handler(input_type=INPUT_TYPE_CONTINUE)
def handle_input_continue(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT
    db.session.add(log_script)
    span = trace.span(name="user_continue", input=input)
    span.end()
    continue_func = CONTINUE_HANDLE_MAP.get(script_info.script_ui_type, None)
    if continue_func:
        continue_func(app, user_id, attend, script_info, input, trace, trace_args)

    db.session.flush()
