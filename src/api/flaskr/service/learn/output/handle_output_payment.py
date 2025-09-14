from flask import Flask
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.order.funs import init_buy_record
from flaskr.service.learn.const import INPUT_TYPE_CONTINUE
from flaskr.service.learn.plugin import (
    register_shifu_output_handler,
)
from flaskr.service.user.models import User
from flaskr.i18n import _
from flaskr.service.learn.utils import get_script_ui_label
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.learn.dtos import ScriptDTO
from flaskr.service.shifu.dtos import PaymentDTO


@register_shifu_output_handler("payment")
def _handle_output_payment(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
) -> ScriptDTO:
    if not is_preview:
        order = init_buy_record(app, user_info.user_id, outline_item_info.shifu_bid)
        if order.status != ORDER_STATUS_SUCCESS:
            payment: PaymentDTO = block_dto.block_content
            title = payment.label
            title = get_script_ui_label(app, title)
            if not title:
                title = _("COMMON.CHECKOUT")
            btn = [{"label": title, "value": order.order_id}]
            return ScriptDTO(
                "order", {"buttons": btn}, outline_item_info.bid, block_dto.bid
            )
    else:
        title = _("COMMON.CONTINUE")
        btn = [
            {
                "label": title,
                "value": title,
                "type": INPUT_TYPE_CONTINUE,
            }
        ]
        return ScriptDTO(
            "buttons",
            {"buttons": btn},
            outline_item_info.bid,
            block_dto.bid,
        )
