from ..plugin import continue_check_handler
from flask import Flask
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.lesson.models import AILessonScript
from trace import Trace
from flaskr.service.user.models import User
from flaskr.service.lesson.const import (
    UI_TYPE_TO_PAY,
)
from flaskr.service.order.models import AICourseBuyRecord
from flaskr.service.order.consts import BUY_STATUS_SUCCESS


@continue_check_handler(UI_TYPE_TO_PAY)
def check_to_pay(
    app: Flask,
    user_info: User,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    order = AICourseBuyRecord.query.filter(
        AICourseBuyRecord.user_id == user_info.user_id,
        AICourseBuyRecord.course_id == attend.course_id,
        AICourseBuyRecord.status == BUY_STATUS_SUCCESS,
    ).first()
    return order is not None
