from trace import Trace
from flask import Flask
from flaskr.api.llm import chat_llm
from flaskr.service.study.const import INPUT_TYPE_ASK, ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.study.models import AICourseLessonAttendScript
from flaskr.service.lesson.models import AILessonScript, AILesson
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.plugin import register_input_handler
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.study.utils import (
    get_follow_up_info,
    get_lesson_system,
    make_script_dto,
    get_fmt_prompt,
)
from flaskr.dao import db
from flaskr.service.study.input_funcs import (
    BreakException,
    check_text_with_llm_response,
    generation_attend,
)
from flaskr.service.user.models import User


@register_input_handler(input_type=INPUT_TYPE_ASK)
@extensible_generic
def handle_input_ask(
    app: Flask,
    user_info: User,
    lesson: AILesson,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):

    follow_up_info = get_follow_up_info(app, script_info)
    app.logger.info("follow_up_info:{}".format(follow_up_info.__json__()))
    history_scripts = (
        AICourseLessonAttendScript.query.filter(
            AICourseLessonAttendScript.attend_id == attend.attend_id,
        )
        .order_by(AICourseLessonAttendScript.id.asc())
        .all()
    )

    messages = []
    input = input.replace("{", "{{").replace("}", "}}")
    system_prompt = get_lesson_system(app, script_info.lesson_id)
    system_message = system_prompt if system_prompt else ""
    # format the system message
    system_message = get_fmt_prompt(app, user_info.user_id, system_message)
    system_message = system_message if system_message else "" + "\n 之前的会话历史为:\n"
    for script in history_scripts:
        if script.script_role == ROLE_STUDENT:
            system_message = system_message + f"学员: {script.script_content}\n"
        elif script.script_role == ROLE_TEACHER:
            system_message = system_message + f"老师: {script.script_content}\n"

    messages.append({"role": "system", "content": system_message})
    messages.append(
        {
            "role": "user",
            "content": get_fmt_prompt(
                app,
                user_info.user_id,
                profile_tmplate=follow_up_info.ask_prompt,
                input=input,
            ),
        }
    )
    # get follow up model
    follow_up_model = follow_up_info.ask_model
    # todo reflact
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT
    # log_script.script_ui_conf = script_info.script_ui_conf
    db.session.add(log_script)
    span = trace.span(name="user_follow_up", input=input)
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
    resp = chat_llm(
        app,
        user_info.user_id,
        span,
        model=follow_up_model,
        json=True,
        stream=True,
        temperature=script_info.script_temprature,
        generation_name="user_follow_ask_"
        + lesson.lesson_no
        + "_"
        + str(script_info.script_index)
        + "_"
        + script_info.script_name,
        messages=messages,
    )
    response_text = ""
    for i in resp:
        current_content = i.result
        if isinstance(current_content, str):
            response_text += current_content
            yield make_script_dto(
                "text", i.result, script_info.script_id, script_info.lesson_id
            )
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = response_text
    log_script.script_role = ROLE_TEACHER
    db.session.add(log_script)
    span.end(output=response_text)
    trace_args["output"] = trace_args["output"] + "\r\n" + response_text
    trace.update(**trace_args)
    db.session.flush()
    yield make_script_dto(
        "text_end", "", script_info.script_id, script_info.lesson_id, log_script.log_id
    )
