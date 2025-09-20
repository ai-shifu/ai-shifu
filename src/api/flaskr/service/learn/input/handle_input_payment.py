from flask import Flask
from flaskr.service.learn.plugin import (
    register_shifu_input_handler,
)
from flaskr.service.order.funs import query_raw_buy_record
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from typing import Generator


@extensible_generic
@register_shifu_input_handler("payment")
def _handle_input_payment(
    app: Flask,
    user_info: User,
    attend_id: str,
    input: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
) -> Generator[str, None, None]:
    shifu_bid = outline_item_info.shifu_bid
    order = query_raw_buy_record(app, user_info.user_id, shifu_bid)
    if order and order.status == ORDER_STATUS_SUCCESS:
        return
    return None
