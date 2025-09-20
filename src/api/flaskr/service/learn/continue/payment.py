from flaskr.service.learn.plugin import register_shifu_continue_handler
from flask import Flask
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.order.models import Order
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS


@register_shifu_continue_handler("payment")
def _handle_continue_payment(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
) -> bool:
    order: Order = Order.query.filter(
        Order.user_bid == user_info.user_id,
        Order.shifu_bid == outline_item_info.shifu_bid,
        Order.status == ORDER_STATUS_SUCCESS,
    ).first()

    if order is None:
        return False
    app.logger.info(f"order: {order.order_bid}")
    return True
