from flask import Flask

from flaskr.service.lesson.const import UI_TYPE_CHECKCODE
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_CHECKCODE
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.study.utils import check_phone_number, get_script_ui_label
from flaskr.service.user.common import send_sms_code_without_check
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.user.models import User


@register_ui_handler(UI_TYPE_CHECKCODE)
def handle_input_checkcode(
    app: Flask,
    user_info: User,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
) -> ScriptDTO:
    if check_phone_number(app, user_info, input):
        expires = send_sms_code_without_check(app, user_info, input)
        expires["content"] = get_script_ui_label(app, script_info.script_ui_content)
        return ScriptDTO(
            INPUT_TYPE_CHECKCODE,
            expires,
            script_info.script_id,
        )
    else:
        app.logger.info("handle_input_checkcode input is not phone number:" + input)
        return ScriptDTO(
            INPUT_TYPE_CHECKCODE,
            script_info.script_ui_content,
            script_info.lesson_id,
            script_info.script_id,
        )
