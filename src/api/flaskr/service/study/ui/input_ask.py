from flask import Flask
from flaskr.service.user.models import User
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.lesson.const import (
    ASK_MODE_ENABLE,
)
from flaskr.service.study.utils import get_follow_up_info
from flaskr.service.study.dtos import ScriptDTO
from flaskr.framework.plugin.plugin_manager import extensible


@extensible
def handle_ask_mode(
    app: Flask,
    user_info: User,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
):
    follow_up_info = get_follow_up_info(app, script_info, attend)
    ask_mode = follow_up_info.ask_mode
    visible = True if ask_mode == ASK_MODE_ENABLE else False
    enable = True if ask_mode == ASK_MODE_ENABLE else False
    return ScriptDTO(
        "ask_mode",
        {"ask_mode": enable, "visible": visible},
        attend.lesson_id,
        script_info.script_id if script_info else "",
    )
