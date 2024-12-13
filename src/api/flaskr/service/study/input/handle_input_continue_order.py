from flask import Flask
from trace import Trace
from flaskr.service.study.plugin import register_continue_handler
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend, AICourseBuyRecord
from flaskr.service.lesson.const import UI_TYPE_TO_PAY
from flaskr.service.order.consts import BUY_STATUS_SUCCESS
from flaskr.service.common import raise_error


# no block order
# geyunfei
#
@register_continue_handler(script_ui_type=UI_TYPE_TO_PAY)
def handle_input_continue_order(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    course_id = attend.course_id
    buy_record = AICourseBuyRecord.query.filter(
        AICourseBuyRecord.course_id == course_id,
        AICourseBuyRecord.user_id == user_id,
        AICourseBuyRecord.status == BUY_STATUS_SUCCESS,
    ).first()
    if not buy_record:
        raise_error("COURSE.COURSE_NOT_PURCHASED")
    return None
