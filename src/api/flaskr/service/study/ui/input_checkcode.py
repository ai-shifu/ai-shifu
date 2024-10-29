import time
from flask import Flask

from flaskr.service.common.models import AppException
from flaskr.service.lesson.const import UI_TYPE_CHECKCODE
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_CHECKCODE
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.study.utils import make_script_dto, check_phone_number
from flaskr.service.user.common import send_sms_code_without_check


@register_ui_handler(UI_TYPE_CHECKCODE)
def handle_input_checkcode(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
):
    try:
        if check_phone_number(app, user_id, input):
            expires = send_sms_code_without_check(app, user_id, input)
            expires["content"] = script_info.script_ui_content
            yield make_script_dto(INPUT_TYPE_CHECKCODE, expires, script_info.script_id)
        else:
            app.logger.info("handle_input_checkcode input is not phone number:" + input)
            yield make_script_dto(
                INPUT_TYPE_CHECKCODE,
                script_info.script_ui_content,
                script_info.script_id,
            )
    except AppException as e:
        for i in e.message:
            yield make_script_dto("text", i, script_info.script_id)
            time.sleep(0.01)
        yield make_script_dto("text_end", "", script_info.script_id)
