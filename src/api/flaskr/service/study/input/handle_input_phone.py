import time
from trace import Trace
from flask import Flask
from flaskr.service.lesson.models import AILessonScript, AILesson
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_PHONE, ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.study.input_funcs import BreakException
from flaskr.service.study.plugin import register_input_handler
from flaskr.service.study.utils import (
    check_phone_number,
    generation_attend,
    make_script_dto,
)
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.user.models import User
from flaskr.service.study.utils import get_script_ui_label


@register_input_handler(input_type=INPUT_TYPE_PHONE)
@extensible_generic
def handle_input_phone(
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
    span = trace.span(name="user_input_phone", input=input)
    response_text = "请输入正确的手机号"
    if not check_phone_number(app, user_info.user_id, input):
        for i in response_text:
            yield make_script_dto(
                "text", i, script_info.script_id, script_info.lesson_id
            )
            time.sleep(0.01)
        yield make_script_dto(
            "text_end", "", script_info.script_id, script_info.lesson_id
        )
        yield make_script_dto(
            INPUT_TYPE_PHONE,
            get_script_ui_label(app, script_info.script_ui_content),
            script_info.script_id,
            script_info.lesson_id,
        )
        log_script = generation_attend(app, attend, script_info)
        log_script.script_content = response_text
        log_script.script_role = ROLE_TEACHER
        db.session.add(log_script)
        span.end(output=response_text)
        db.session.flush()
        raise BreakException
    span.end()
