from flask import Flask
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.lesson.const import UI_TYPE_INPUT
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.user.models import User
from flaskr.service.study.utils import get_script_ui_label


@register_ui_handler(UI_TYPE_INPUT)
def handle_input_text(
    app: Flask,
    user_info: User,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
) -> ScriptDTO:
    return ScriptDTO(
        "input",
        {"content": get_script_ui_label(app, script_info.script_ui_content)},
        script_info.lesson_id,
        script_info.script_id,
    )
