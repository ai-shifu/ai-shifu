from flaskr.service.study.plugin import register_shifu_continue_handler
from flask import Flask
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient


@register_shifu_continue_handler("login")
def _handle_continue_login(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    app.logger.info(f"check_login {user_info.user_state}")
    return user_info.user_state != 0
