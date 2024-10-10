from flask import Flask
from flaskr.service.lesson.const import UI_TYPE_TO_PAY
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.consts import BUY_STATUS_SUCCESS
from flaskr.service.order.funs import init_buy_record
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_CONTINUE
from flaskr.service.study.plugin import register_ui_handler
from flaskr.service.study.utils import make_script_dto


@register_ui_handler(UI_TYPE_TO_PAY)
def handle_input_to_pay(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
):
    order = init_buy_record(app, user_id, attend.course_id)
    if order.status != BUY_STATUS_SUCCESS:
        btn = [{"label": script_info.script_ui_content, "value": order.order_id}]
        yield make_script_dto(
            "order", {"title": "买课！", "buttons": btn}, script_info.script_id
        )
    else:
        btn = [
            {
                "label": script_info.script_ui_content,
                "value": script_info.script_ui_content,
                "type": INPUT_TYPE_CONTINUE,
            }
        ]
        yield make_script_dto(
            "buttons", {"title": "接下来", "buttons": btn}, script_info.script_id
        )
