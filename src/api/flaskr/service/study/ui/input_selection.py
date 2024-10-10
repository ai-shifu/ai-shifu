import json
from flask import Flask
from flaskr.service.lesson.const import UI_TYPE_SELECTION
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_SELECT
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.study.utils import make_script_dto


@register_ui_handler(UI_TYPE_SELECTION)
def handle_input_selection(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
):
    btns = json.loads(script_info.script_other_conf)["btns"]
    for btn in btns:
        btn["type"] = INPUT_TYPE_SELECT
    yield make_script_dto(
        "buttons",
        {"title": script_info.script_ui_content, "buttons": btns},
        script_info.script_id,
    )
