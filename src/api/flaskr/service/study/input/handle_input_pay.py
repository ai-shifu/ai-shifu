from trace import Trace
from flask import Flask
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_PAY
from flaskr.service.study.plugin import register_input_handler
from flaskr.service.order.funs import query_raw_buy_record
from flaskr.service.order.consts import BUY_STATUS_SUCCESS
from flaskr.framework.plugin.plugin_manager import extensible_generic


@register_input_handler(input_type=INPUT_TYPE_PAY)
@extensible_generic
def handle_input_pay(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    course_id = attend.course_id
    order = query_raw_buy_record(app, user_id, course_id)
    if order and order.status == BUY_STATUS_SUCCESS:
        return
    return None
