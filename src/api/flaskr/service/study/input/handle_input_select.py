import json
from trace import Trace
from flask import Flask
from flaskr.service.profile.funcs import save_user_profiles
from flaskr.service.lesson.models import AILessonScript, AILesson
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_SELECT, ROLE_STUDENT
from flaskr.service.study.plugin import register_input_handler
from flaskr.service.study.utils import generation_attend, get_profile_array
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.study.ui.input_selection import handle_input_selection
from flaskr.service.user.models import User


@register_input_handler(input_type=INPUT_TYPE_SELECT)
@extensible_generic
def handle_input_select(
    app: Flask,
    user_info: User,
    lesson: AILesson,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    profile_keys = get_profile_array(script_info.script_ui_profile)
    profile_tosave = {}
    if len(profile_keys) == 0:
        # btns = json.loads(script_info.script_other_conf)
        other_conf = script_info.script_other_conf or "{}"
        try:
            btns = json.loads(other_conf)
        except json.JSONDecodeError as e:
            app.logger.error(
                f"Invalid JSON in script_other_conf: {other_conf}, error: {str(e)}"
            )
            btns = {}
        conf_key = btns.get("var_name", "input")
        profile_tosave[conf_key] = input
    for k in profile_keys:
        profile_tosave[k] = input
    save_user_profiles(app, user_info.user_id, lesson.course_id, profile_tosave)
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT
    log_script.script_ui_conf = json.dumps(
        handle_input_selection(
            app, user_info, attend, script_info, input, trace, trace_args
        ).__json__()
    )
    db.session.add(log_script)
    span = trace.span(name="user_select", input=input)
    span.end()
    db.session.flush()
