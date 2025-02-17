from flask import Flask

from flaskr.service.lesson.const import UI_TYPE_BUTTON
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.study.const import INPUT_TYPE_CONTINUE
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.user.models import User


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
    app.logger.info("handle_input_button:{}".format(script_info.script_ui_content))
    if script_info.script_ui_content == "继续":
        display = False
    else:
        display = True
    btn = [
        {
            "label": script_info.script_ui_content,
            "value": script_info.script_ui_content,
            "type": INPUT_TYPE_CONTINUE,
            "display": display,
        }
    ]
    return ScriptDTO(
        "buttons",
        {"title": "接下来", "buttons": btn},
        script_info.lesson_id,
        script_info.script_id,
    )
