from flaskr.service.study.plugin import register_shifu_continue_handler
from flask import Flask
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.order.models import AICourseBuyRecord
from flaskr.service.order.consts import BUY_STATUS_SUCCESS


@register_shifu_continue_handler("payment")
def _handle_continue_order(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    order = AICourseBuyRecord.query.filter(
        AICourseBuyRecord.user_id == user_info.user_id,
        AICourseBuyRecord.course_id == outline_item_info.shifu_bid,
        AICourseBuyRecord.status == BUY_STATUS_SUCCESS,
    ).first()

    if order is None:
        return False
    app.logger.info(f"order: {order.order_id}")
    return True
