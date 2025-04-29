import time
from trace import Trace
from flask import Flask
from flaskr.api.llm import invoke_llm
from flaskr.service.profile.funcs import save_user_profiles
from flaskr.service.study.input_funcs import (
    BreakException,
    check_text_with_llm_response,
)
from flaskr.service.lesson.models import AILessonScript, AILesson
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.const import INPUT_TYPE_TEXT, ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.study.plugin import register_input_handler
from flaskr.service.study.utils import (
    extract_json,
    generation_attend,
    get_fmt_prompt,
    make_script_dto,
    get_model_setting,
)
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
import json
from flaskr.service.study.ui.input_text import handle_input_text as handle_input_text_ui
from flaskr.service.user.models import User


@register_input_handler(input_type=INPUT_TYPE_TEXT)
@extensible_generic
def handle_input_text(
    app: Flask,
    user_info: User,
    lesson: AILesson,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    model_setting = get_model_setting(app, script_info)
    app.logger.info(f"model_setting: {model_setting.__json__()}")
    prompt = get_fmt_prompt(
        app,
        user_info.user_id,
        attend.course_id,
        script_info.script_check_prompt,
        input,
        script_info.script_profile,
    )
    # todo 换成通用的
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT
    log_script.script_ui_conf = json.dumps(
        handle_input_text_ui(
            app, user_info, attend, script_info, input, trace, trace_args
        ).__json__()
    )
    db.session.add(log_script)
    span = trace.span(name="user_input", input=input)
    res = check_text_with_llm_response(
        app, user_info.user_id, log_script, input, span, lesson, script_info, attend
    )
    try:
        first_value = next(res)
        app.logger.info("check_text_by_edun is not None")
        yield first_value
        yield from res
        db.session.flush()
        raise BreakException
    except StopIteration:
        app.logger.info("check_text_by_edun is None ,invoke_llm")

    resp = invoke_llm(
        app,
        user_info.user_id,
        span,
        model=model_setting.model_name,
        json=True,
        stream=True,
        message=prompt,
        generation_name="user_input_"
        + lesson.lesson_no
        + "_"
        + str(script_info.script_index)
        + "_"
        + script_info.script_name,
        **model_setting.model_args,
    )
    response_text = ""
    check_success = False
    for i in resp:
        current_content = i.result
        if isinstance(current_content, str):
            response_text += current_content
    jsonObj = extract_json(app, response_text)
    check_success = jsonObj.get("result", "") == "ok"
    if check_success:
        app.logger.info("check success")
        profile_tosave = jsonObj.get("parse_vars")
        save_user_profiles(app, user_info.user_id, lesson.course_id, profile_tosave)
        for key in profile_tosave:
            yield make_script_dto(
                "profile_update",
                {"key": key, "value": profile_tosave[key]},
                script_info.script_id,
                script_info.lesson_id,
            )
            time.sleep(0.01)
        span.end()
        db.session.flush()

    else:
        reason = jsonObj.get("reason", response_text)
        for text in reason:
            yield make_script_dto(
                "text", text, script_info.script_id, script_info.lesson_id
            )
            time.sleep(0.01)
        log_script = generation_attend(app, attend, script_info)
        log_script.script_content = reason
        log_script.script_role = ROLE_TEACHER
        db.session.add(log_script)
        span.end(output=response_text)
        trace_args["output"] = trace_args["output"] + "\r\n" + response_text
        trace.update(**trace_args)
        db.session.flush()
        yield make_script_dto(
            "text_end",
            "",
            script_info.script_id,
            script_info.lesson_id,
            log_script.log_id,
        )
        yield make_script_dto(
            "input",
            script_info.script_ui_content,
            script_info.script_id,
            script_info.lesson_id,
            log_script.log_id,
        )
        raise BreakException
