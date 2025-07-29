from flask import Flask
from flaskr.service.study.const import ROLE_STUDENT
from flaskr.service.study.plugin import (
    SHIFU_CONTINUE_HANDLER_MAP,
)
from flaskr.service.study.utils import generation_attend, get_script_ui_label
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.study.plugin import register_shifu_continue_handler


@register_shifu_continue_handler("continue")
@extensible_generic
def _handle_input_continue(
    app: Flask,
    user_info: User,
    attend_id: str,
    input: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    if block_dto.block_content:
        # The continue button has a non-default label
        log_script = generation_attend(
            app, user_info, attend_id, outline_item_info, block_dto
        )
        log_script.script_content = get_script_ui_label(app, block_dto.block_content)
        log_script.script_role = ROLE_STUDENT
        db.session.add(log_script)
        span = trace.span(name="user_continue", input=input)
        span.end()
        db.session.flush()

    continue_func = SHIFU_CONTINUE_HANDLER_MAP.get(block_dto.type, None)

    if continue_func:
        app.logger.info(f"continue_func: {continue_func.__name__}")
        continue_func(
            app, user_info, attend_id, outline_item_info, block_dto, trace_args, trace
        )
