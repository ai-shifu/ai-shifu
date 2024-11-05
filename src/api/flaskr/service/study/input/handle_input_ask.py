from trace import Trace
from flask import Flask
from flaskr.api.llm import chat_llm
from flaskr.service.study.const import INPUT_TYPE_ASK, ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.study.models import AICourseLessonAttendScript
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.plugin import register_input_handler
from flaskr.service.study.utils import (
    get_follow_up_info,
    get_lesson_system,
    make_script_dto,
    get_fmt_prompt,
)
from flaskr.dao import db
from flaskr.service.study.input_funcs import (
    BreakException,
    check_text_by_edun,
    generation_attend,
)


@register_input_handler(input_type=INPUT_TYPE_ASK)
def handle_input_ask(
    app: Flask,
    user_id: str,
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

    # the old logic
    #    messages = []
    #    messages.append({"role": "user", "content": "你是老师，请扮演老师的角色回答学员的追问。"})
    #    for script in history_scripts:
    #        if script.script_content is None or script.script_content.strip() == "":
    #            continue
    #        if script.script_role == ROLE_STUDENT:
    #            if messages[-1].get("role", "") != "user":
    #                messages.append({"role": "user", "content": script.script_content})
    #            else:
    #                messages[-1]["content"] += "\n" + script.script_content
    #        elif script.script_role == ROLE_TEACHER:
    #            if messages[-1].get("role", "") != "assistant":
    #                messages.append({"role": "assistant", "content": script.script_content})
    #            else:
    #                messages[-1]["content"] += "\n" + script.script_content
    #    # get system prompt
    #    system_prompt = get_lesson_system(app, script_info.lesson_id)
    #    if system_prompt:
    #        # add system prompt to messages first
    #        messages.insert(0, {"role": "system", "content": system_prompt})
    #    # get follow up ask prompt
    #    follow_up_ask_prompt = follow_up_info.ask_prompt
    #    messages.append(
    #        {"role": "user", "content": follow_up_ask_prompt.format(input=input)}
    #    )
    #
    # the new logic
    messages = []
    # replace the { } with the actual content
    input = input.replace("{", "{{").replace("}", "}}")
    system_prompt = get_lesson_system(app, script_info.lesson_id)
    system_message = system_prompt if system_prompt else ""
    # format the system message
    system_message = get_fmt_prompt(app, user_id, system_message)
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
                app, user_id, profile_tmplate=follow_up_info.ask_prompt, input=input
            ),
        }
    )
    # get follow up model
    follow_up_model = follow_up_info.ask_model
    # todo 换成通用的
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT
    db.session.add(log_script)
    span = trace.span(name="user_follow_up", input=input)
    res = check_text_by_edun(app, user_id, log_script, input, span, script_info, attend)
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
        span,
        model=follow_up_model,
        json=True,
        stream=True,
        temperature=script_info.script_temprature,
        messages=messages,
    )
    response_text = ""
    for i in resp:
        current_content = i.result
        if isinstance(current_content, str):
            response_text += current_content
            yield make_script_dto("text", i.result, script_info.script_id)
    yield make_script_dto("text_end", "", script_info.script_id)
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = response_text
    log_script.script_role = ROLE_TEACHER
    db.session.add(log_script)
    span.end(output=response_text)
    trace_args["output"] = trace_args["output"] + "\r\n" + response_text
    trace.update(**trace_args)
    db.session.flush()
