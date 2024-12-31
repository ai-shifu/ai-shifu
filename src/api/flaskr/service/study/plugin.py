from flask import Flask
from trace import Trace
from flaskr.service.study.ui.input_ask import handle_ask_mode
from flaskr.service.common.models import AppException
from flaskr.service.lesson.models import AILessonScript, AILesson
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.dao import db


# handlers for input
INPUT_HANDLE_MAP = {}
# spceic handler for input continue
CONTINUE_HANDLE_MAP = {}

# handlers for ui
UI_HANDLE_MAP = {}

# handlers for ui record
UI_RECORD_HANDLE_MAP = {}


# register input for input
# ex. text,continue,start ...
def register_input_handler(input_type: str):
    def decorator(func):
        from flask import current_app

        current_app.logger.info(
            f"register_input_handler {input_type} ==> {func.__name__}"
        )
        INPUT_HANDLE_MAP[input_type] = func
        return func

    return decorator


# register continue for input
# ex. continue,start ...
def register_continue_handler(script_ui_type: int):
    def decorator(func):
        from flask import current_app

        current_app.logger.info(
            f"register_continue_handler {script_ui_type} ==> {func.__name__}"
        )
        CONTINUE_HANDLE_MAP[script_ui_type] = func
        return func

    return decorator


def register_ui_handler(ui_type):
    def decorator(func):
        from flask import current_app

        current_app.logger.info(f" {ui_type} ==> {func.__name__}")
        UI_HANDLE_MAP[ui_type] = func
        return func

    return decorator


def handle_input(
    app: Flask,
    user_id: str,
    input_type: str,
    lesson: AILesson,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    app.logger.info(f"handle_input {input_type},user_id:{user_id},input:{input} ")
    if input_type in INPUT_HANDLE_MAP:
        respone = INPUT_HANDLE_MAP[input_type](
            app, user_id, lesson, attend, script_info, input, trace, trace_args
        )
        if respone:
            yield from respone
    else:
        app.logger.info(UI_HANDLE_MAP.keys())
        return None


def handle_ui(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace,
    trace_args,
):
    if script_info.script_ui_type in UI_HANDLE_MAP:
        app.logger.info(
            "generation ui lesson_id:{}  script type:{},user_id:{},script_index:{}".format(
                script_info.lesson_id,
                script_info.script_type,
                user_id,
                script_info.script_index,
            )
        )
        ret = []
        ret.append(
            UI_HANDLE_MAP[script_info.script_ui_type](
                app, user_id, attend, script_info, input, trace, trace_args
            )
        )
        ret.append(
            handle_ask_mode(app, user_id, attend, script_info, input, trace, trace_args)
        )
        span = trace.span(name="ui_script")
        span.end()
        db.session.flush()
        return ret
    else:
        raise AppException("script type not found")


def generate_ui(
    app: Flask,
    user_id: str,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    if script_info.script_ui_type in UI_HANDLE_MAP:
        yield from UI_HANDLE_MAP[script_info.script_ui_type](
            app, user_id, attend, script_info, input, trace, trace_args
        )
    else:
        raise AppException("script type not found")
