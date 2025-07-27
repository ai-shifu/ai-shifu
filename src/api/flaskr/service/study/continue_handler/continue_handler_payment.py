from flask import Flask
from flaskr.service.shifu.adapter import BlockDTO
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from langfuse.client import StatefulTraceClient
from flaskr.service.user.models import User


def _continue_handler_payment(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    return True
