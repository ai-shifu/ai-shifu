from flask import Flask
from trace import Trace
from flaskr.service.common.models import AppException
from flaskr.service.lesson.models import AILessonScript
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.dao import db
from flaskr.service.user.models import User
from flaskr.service.study.output.ui_continue import make_continue_ui
from functools import wraps
from flaskr.service.shifu.adapter import BlockDTO
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from langfuse.client import StatefulTraceClient
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.study.utils import make_script_dto_to_stream
from flaskr.service.study.output.ask import _handle_output_ask

# handlers for input
INPUT_HANDLE_MAP = {}
# spceic handler for input continue
CONTINUE_HANDLE_MAP = {}

# handlers for ui
UI_HANDLE_MAP = {}

# handlers for ui record
UI_RECORD_HANDLE_MAP = {}


# handlers for continue
CONTINUE_CHECK_HANDLE_MAP = {}


def unwrap_function(func):
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    return func


# register input for input
# ex. text,continue,start ...
def register_input_handler(input_type: str):
    def decorator(func):
        from flask import current_app

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        current_app.logger.info(
            f"register_input_handler {input_type} ==>  {func.__name__}"
        )
        INPUT_HANDLE_MAP[input_type] = wrapper
        return wrapper

    return decorator


# register continue for input
# ex. continue,start ...
def register_continue_handler(script_ui_type: int):
    def decorator(func):
        from flask import current_app

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        current_app.logger.info(
            f"register_continue_handler {script_ui_type} ==> {func.__name__}    "
        )
        CONTINUE_HANDLE_MAP[script_ui_type] = wrapper
        return wrapper

    return decorator


# register ui handler
# to return the ui to frontend
def register_ui_handler(ui_type):
    def decorator(func):
        from flask import current_app

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        current_app.logger.info(f"register_ui_handler {ui_type} ==>  {func.__name__}")
        UI_HANDLE_MAP[ui_type] = func
        return wrapper

    return decorator


# register continue handler
# to check whether to get next script
def continue_check_handler(script_ui_type: int):
    def decorator(func):
        from flask import current_app

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        current_app.logger.info(
            f"continue_check_handler {script_ui_type} ==> {func.__name__}"
        )
        CONTINUE_CHECK_HANDLE_MAP[script_ui_type] = wrapper
        return wrapper

    return decorator


def handle_input(
    app: Flask,
    user_info: User,
    lesson: ShifuOutlineItemDto,
    attend: AICourseLessonAttend,
    block_dto: BlockDTO,
    input: str,
    trace: Trace,
    trace_args,
):
    app.logger.info(
        f"handle_block {block_dto.type},user_id:{user_info.user_id},input:{input} "
    )
    if block_dto.type in INPUT_HANDLE_MAP:
        respone = INPUT_HANDLE_MAP[block_dto.type](
            app, user_info, lesson, attend, block_dto, trace, trace_args
        )
        if respone:
            yield from respone
    else:
        app.logger.info(INPUT_HANDLE_MAP.keys())
        return None


def handle_ui(
    app: Flask,
    user_info: User,
    attend: AICourseLessonAttend,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    input: str,
    trace,
    trace_args,
):
    app.logger.info(f"handle_ui {block_dto.type}")
    if block_dto.type in SHIFU_OUTPUT_HANDLER_MAP:
        app.logger.info(
            "generation ui lesson_id:{}  script type:{},user_id:{},script_index:{}".format(
                attend.lesson_id,
                block_dto.type,
                user_info.user_id,
                attend.script_index,
            )
        )
        ret = []
        if check_block_continue(
            app,
            user_info,
            attend.attend_id,
            outline_item_info,
            block_dto,
            trace_args,
            trace,
        ):
            app.logger.info("check_continue true ,make continue ui")
            ret.append(
                make_continue_ui(
                    app,
                    user_info,
                    attend.attend_id,
                    outline_item_info,
                    block_dto,
                    trace_args,
                    trace,
                )
            )
        else:
            app.logger.info("check_continue false ,make ui")
            ret.append(
                SHIFU_OUTPUT_HANDLER_MAP[block_dto.type](
                    app,
                    user_info,
                    attend,
                    outline_item_info,
                    block_dto,
                    trace_args,
                    trace,
                )
            )
        ret.append(
            _handle_output_ask(
                app,
                user_info,
                attend.attend_id,
                outline_item_info,
                block_dto,
                trace_args,
                trace,
            )
        )
        span = trace.span(name="ui_script")
        span.end()
        db.session.flush()
        return ret
    else:
        raise AppException("script type not found")


def generate_ui(
    app: Flask,
    user_info: User,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    if check_continue(app, user_info, attend, script_info, input, trace, trace_args):
        return make_continue_ui(
            app, user_info, attend, script_info, input, trace, trace_args
        )
    if script_info.script_ui_type in UI_HANDLE_MAP:
        yield from UI_HANDLE_MAP[script_info.script_ui_type](
            app, user_info, attend, script_info, input, trace, trace_args
        )
    else:
        raise AppException("script type not found")


def check_continue(
    app: Flask,
    user_info: User,
    attend: AICourseLessonAttend,
    script_info: AILessonScript,
    input: str,
    trace: Trace,
    trace_args,
):
    app.logger.info(f"check_continue {script_info.script_ui_type}")
    if script_info.script_ui_type in CONTINUE_CHECK_HANDLE_MAP:
        app.logger.info(f"check_continue {script_info.script_ui_type}")
        return CONTINUE_CHECK_HANDLE_MAP[script_info.script_ui_type](
            app, user_info, attend, script_info, input, trace, trace_args
        )
    return False


# save input,output,continue,continue_check handler for blocks
SHIFU_INPUT_HANDLER_MAP = {}
SHIFU_OUTPUT_HANDLER_MAP = {}
SHIFU_CONTINUE_HANDLER_MAP = {}
SHIFU_CONTINUE_CHECK_HANDLER_MAP = {}


def register_shifu_input_handler(block_type: str):
    def decorator(func):
        from flask import current_app

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        current_app.logger.info(
            f"register_shifu_input_handler {block_type} ==> {func.__name__}"
        )
        SHIFU_INPUT_HANDLER_MAP[block_type] = wrapper
        return wrapper

    return decorator


def register_shifu_output_handler(block_type: str):
    def decorator(func):
        from flask import current_app

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        current_app.logger.info(
            f"register_shifu_output_handler {block_type} ==> {func.__name__}"
        )
        SHIFU_OUTPUT_HANDLER_MAP[block_type] = wrapper
        return wrapper

    return decorator


def register_shifu_continue_handler(block_type: str):
    def decorator(func):
        from flask import current_app

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        current_app.logger.info(
            f"register_shifu_continue_handler {block_type} ==> {func.__name__}"
        )
        SHIFU_CONTINUE_HANDLER_MAP[block_type] = wrapper
        return wrapper

    return decorator


def handle_block_input(
    app: Flask,
    user_info: User,
    attend_id: str,
    input: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    if block_dto.type in SHIFU_INPUT_HANDLER_MAP:
        res = SHIFU_INPUT_HANDLER_MAP[block_dto.type](
            app,
            user_info,
            attend_id,
            input,
            outline_item_info,
            block_dto,
            trace_args,
            trace,
        )
        if res:
            yield from res
    else:
        app.logger.warning(f"shifu input handler not found {block_dto.type}")
    return None


def handle_block_output(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    if block_dto.type in SHIFU_OUTPUT_HANDLER_MAP:
        res = SHIFU_OUTPUT_HANDLER_MAP[block_dto.type](
            app, user_info, attend_id, outline_item_info, block_dto, trace_args, trace
        )
        if isinstance(res, ScriptDTO):
            yield make_script_dto_to_stream(res)
            yield make_script_dto_to_stream(
                _handle_output_ask(
                    app,
                    user_info,
                    attend_id,
                    outline_item_info,
                    block_dto,
                    trace_args,
                    trace,
                )
            )
        else:
            yield from res
    else:
        app.logger.warning(f"shifu output handler not found {block_dto.type}")
    return None


def check_block_continue(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    if block_dto.type in SHIFU_CONTINUE_HANDLER_MAP:
        return SHIFU_CONTINUE_HANDLER_MAP[block_dto.type](
            app, user_info, attend_id, outline_item_info, block_dto, trace_args, trace
        )
    return False
