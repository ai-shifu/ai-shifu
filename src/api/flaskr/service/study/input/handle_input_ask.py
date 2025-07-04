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
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.llm.funcs import format_script_prompt
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


@register_input_handler(
    input_type=INPUT_TYPE_ASK
)  # Register input handler for Q&A type
@extensible_generic
def handle_input_ask(
    app: Flask,  # Flask application instance
    user_info: User,  # User information
    lesson: AILesson,  # shifu information
    attend: AICourseLessonAttend,  # shifu attendance record
    script_info: AILessonScript,  # Script information
    input: str,  # User input question
    trace: Trace,  # Trace object
    trace_args,  # Trace arguments
):
    """
    Main function to handle user Q&A input
    Responsible for processing user questions in the shifu and returning AI tutor responses
    """

    # Get follow-up information (including Q&A prompts and model configuration)
    follow_up_info = get_follow_up_info(app, script_info)
    app.logger.info("follow_up_info:{}".format(follow_up_info.__json__()))

    # Query historical conversation records, ordered by time
    history_scripts = (
        AICourseLessonAttendScript.query.filter(
            AICourseLessonAttendScript.attend_id == attend.attend_id,
        )
        .order_by(AICourseLessonAttendScript.id.asc())
        .all()
    )

    messages = []  # List to store conversation messages
    input = input.replace("{", "{{").replace(
        "}", "}}"
    )  # Escape braces to avoid formatting conflicts
    system_prompt = get_lesson_system(
        app, script_info.lesson_id
    )  # Get shifu system prompt

    # Obtain user configuration information to replace system variables
    user_profiles = get_user_profiles(app, user_info.user_id, attend.course_id)

    # Format the system prompt and replace the variables within it
    system_message = (
        format_script_prompt(system_prompt, user_profiles) if system_prompt else ""
    )

    # Format shifu Q&A prompt, insert system prompt
    system_message = lesson.ask_prompt.replace("{shifu_system_message}", system_message)
    messages.append({"role": "system", "content": system_message})  # Add system message

    # Add historical conversation records to system messages
    for script in history_scripts:
        if script.script_role == ROLE_STUDENT:
            messages.append(
                {"role": "user", "content": script.script_content}
            )  # Add user message
        elif script.script_role == ROLE_TEACHER:
            messages.append(
                {"role": "assistant", "content": script.script_content}
            )  # Add assistant message

    # Start knowledge base retrieval
    time_1 = time.time()
    retrieval_result_list = []  # Store retrieval results
    shifu_id = lesson.course_id
    my_filter = ""
    limit = 3  # Maximum 3 results per knowledge base
    output_fields = ["text"]  # Only return text fields

    # Get course-related knowledge base list
    kb_list = get_kb_list(app, [], [shifu_id])

    # Iterate through each knowledge base for retrieval
    for kb in kb_list:
        retrieval_result = retrieval_fun(
            kb_id=kb["kb_id"],
            query=input,  # Use user input as query
            my_filter=my_filter,
            limit=limit,
            output_fields=output_fields,
        )
        retrieval_result_list.append(retrieval_result)
        # break

    # Merge all retrieval results
    all_retrieval_result = "\n\n".join(retrieval_result_list)
    time_2 = time.time()
    app.logger.info(f"all retrieval_fun takes: {time_2 - time_1}s")
    app.logger.info(f"all_retrieval_result: {all_retrieval_result}")

    # Build user message, including retrieved relevant knowledge
    # user_content = get_fmt_prompt(
    #             app,
    #             user_info.user_id,
    #             attend.course_id,
    #             follow_up_info.ask_prompt,  # Use configured Q&A prompt
    #             input=f"Known '{all_retrieval_result}', please answer '{input}'",  # Combine retrieval results and user question
    #         )

    messages.append(
        {
            "role": "user",
            "content": input,
        }
    )
    app.logger.info(f"messages: {messages}")

    # Get model for follow-up Q&A
    follow_up_model = follow_up_info.ask_model
    if not follow_up_model:
        follow_up_model = app.config.get("DEFAULT_LLM_MODEL", "")

    # Log user input to database
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT  # Mark as student role
    log_script.script_ui_type = UI_TYPE_ASK  # Mark as Q&A type
    db.session.add(log_script)

    # Create trace span
    span = trace.span(name="user_follow_up", input=input)

    # Format prompt for content checking
    prompt = get_fmt_prompt(
        app,
        user_info.user_id,
        attend.course_id,
        script_info.script_prompt,
        input,
        script_info.script_profile,
    )

    # Check if user input needs special processing (such as sensitive word filtering, etc.)
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
        # If check result is not empty, return check result directly
        first_value = next(res)
        app.logger.info("check_text_by_edun is not None")
        yield first_value
        yield from res
        db.session.flush()
        raise BreakException  # Throw break exception to end processing
    except StopIteration:
        app.logger.info("check_text_by_edun is None ,invoke_llm")

    # Call LLM to generate response
    resp = chat_llm(
        app,
        user_info.user_id,
        span,
        model=follow_up_model,  # Use configured model
        json=True,
        stream=True,  # Enable streaming output
        temperature=script_info.script_temperature,  # Use configured temperature parameter
        generation_name="user_follow_ask_"  # Generation task name
        + lesson.lesson_no
        + "_"
        + str(script_info.script_index)
        + "_"
        + script_info.script_name,
        messages=messages,  # Pass complete conversation history
    )

    response_text = ""  # Store complete response text
    # Stream process LLM response
    for i in resp:
        current_content = i.result
        if isinstance(current_content, str):
            response_text += current_content
            # Return each text fragment in real-time
            yield make_script_dto(
                "text", i.result, script_info.script_id, script_info.lesson_id
            )

    # Log AI response to database
    log_script = generation_attend(app, attend, script_info)
    log_script.script_content = response_text
    log_script.script_role = ROLE_TEACHER  # Mark as teacher role
    log_script.script_ui_type = UI_TYPE_ASK  # Mark as Q&A type
    db.session.add(log_script)

    # End trace span
    span.end(output=response_text)
    trace_args["output"] = trace_args["output"] + "\r\n" + response_text
    trace.update(**trace_args)
    db.session.flush()

    # Return end marker
    yield make_script_dto(
        "text_end", "", script_info.script_id, script_info.lesson_id, log_script.log_id
    )
