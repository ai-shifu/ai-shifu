from flask import Flask
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.order.funs import query_raw_buy_record
from flaskr.service.order.consts import BUY_STATUS_SUCCESS
from flaskr.service.study.plugin import register_shifu_input_handler


@register_shifu_input_handler("payment")
def _input_handler_payment(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    app.logger.info(f"_input_handler_payment {block_dto.bid} {outline_item_info.bid}")
    shifu_id = outline_item_info.shifu_bid
    order = query_raw_buy_record(app, user_info.user_id, shifu_id)
    if order and order.status == BUY_STATUS_SUCCESS:
        return
    app.logger.info("line 24")
    return None
