from flask import Flask
from flaskr.service.common.models import AppException
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
from flaskr.service.study.output.handle_output_ask import _handle_output_ask


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
    input_type: str,
    input: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    app.logger.info(f"handle_block_input {block_dto.type}")
    block_type = block_dto.type
    if input_type == "ask":
        block_type = "ask"
    if block_type in SHIFU_INPUT_HANDLER_MAP:
        res = SHIFU_INPUT_HANDLER_MAP[block_type](
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
        result = SHIFU_CONTINUE_HANDLER_MAP[block_dto.type](
            app, user_info, attend_id, outline_item_info, block_dto, trace_args, trace
        )
    else:
        app.logger.info(f"check_block_continue {block_dto.type} not found")
        result = False
    app.logger.info(f"check_block_continue {block_dto.type} {result}")
    return result
