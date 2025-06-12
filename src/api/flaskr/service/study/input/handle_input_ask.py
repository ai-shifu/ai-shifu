import time
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
from flaskr.service.rag.funs import (
    get_kb_list,
    retrieval_fun,
)
from flaskr.service.lesson.const import UI_TYPE_ASK


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
    system_message = get_fmt_prompt(
        app, user_info.user_id, attend.course_id, system_message
    )
    system_message = system_message if system_message else "" + "\n 之前的会话历史为:\n"
    for script in history_scripts:
        if script.script_role == ROLE_STUDENT:
            system_message = system_message + f"学员: {script.script_content}\n"
        elif script.script_role == ROLE_TEACHER:
            system_message = system_message + f"老师: {script.script_content}\n"

    messages.append({"role": "system", "content": system_message})

    time_1 = time.time()
    retrieval_result_list = []
    course_id = lesson.course_id
    my_filter = ""
    limit = 3
    output_fields = ["text"]
    kb_list = get_kb_list(app, [], [course_id])
    for kb in kb_list:
        retrieval_result = retrieval_fun(
            kb_id=kb["kb_id"],
            query=input,
            my_filter=my_filter,
            limit=limit,
            output_fields=output_fields,
        )
        retrieval_result_list.append(retrieval_result)
        # break
    all_retrieval_result = "\n\n".join(retrieval_result_list)
    time_2 = time.time()
    app.logger.info(f"all retrieval_fun takes: {time_2 - time_1}s")
    app.logger.info(f"all_retrieval_result: {all_retrieval_result}")

    messages.append(
        {
            "role": "user",
            "content": get_fmt_prompt(
                app,
                user_info.user_id,
                attend.course_id,
                follow_up_info.ask_prompt,
                input=f"已知'{all_retrieval_result}'，请问'{input}'",
            ),
        }
    )

    app.logger.info(f"messages: {messages}")

    # get follow up model
    follow_up_model = follow_up_info.ask_model
    # todo reflact
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT
    log_script.script_ui_type = UI_TYPE_ASK
    db.session.add(log_script)
    span = trace.span(name="user_follow_up", input=input)
    prompt = get_fmt_prompt(
        app,
        user_info.user_id,
        attend.course_id,
        script_info.script_prompt,
        input,
        script_info.script_profile,
    )
    res = check_text_with_llm_response(
        app,
        user_info.user_id,
        log_script,
        input,
        span,
        lesson,
        script_info,
        attend,
        prompt,
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
    log_script.script_ui_type = UI_TYPE_ASK
    db.session.add(log_script)
    span.end(output=response_text)
    trace_args["output"] = trace_args["output"] + "\r\n" + response_text
    trace.update(**trace_args)
    db.session.flush()
    yield make_script_dto(
        "text_end", "", script_info.script_id, script_info.lesson_id, log_script.log_id
    )
