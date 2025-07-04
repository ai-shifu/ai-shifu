from flask import Flask

from flaskr.service.lesson.const import UI_TYPE_BUTTON
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.study.const import INPUT_TYPE_CONTINUE
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.user.models import User
from flaskr.service.study.utils import get_script_ui_label
from flaskr.i18n import _


@register_ui_handler(UI_TYPE_BUTTON)
def handle_input_button(
    app: Flask,
    user_info: User,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
) -> ScriptDTO:
    msg = script_info.script_ui_content
    display = bool(msg)  # Set display based on whether msg has content
    if not msg:
        msg = _("COMMON.CONTINUE")  # Assign default message if msg is empty

    app.logger.info("handle_input_button:{}".format(msg))

    # if is json
    msg = get_script_ui_label(app, msg)

    btn = [
        {
            "label": msg,
            "value": msg,
            "type": INPUT_TYPE_CONTINUE,
            "display": display,
        }
    ]

    return ScriptDTO(
        "buttons",
        {"buttons": btn},
        script_info.lesson_id,
        script_info.script_id,
    )
