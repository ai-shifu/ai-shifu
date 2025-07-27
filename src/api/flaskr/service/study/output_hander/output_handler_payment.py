from flask import Flask
from flaskr.service.shifu.adapter import BlockDTO
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from langfuse.client import StatefulTraceClient
from flaskr.service.user.models import User
from flaskr.service.order.consts import BUY_STATUS_SUCCESS
from flaskr.service.order import init_buy_record
from flaskr.service.study.utils import get_script_ui_label, make_script_dto
from flaskr.i18n import _
from flaskr.service.study.const import INPUT_TYPE_CONTINUE
from flaskr.service.shifu.dtos import PaymentDTO
from flaskr.service.study.plugin import register_shifu_output_handler


@register_shifu_output_handler("payment")
def _output_handler_payment(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    app.logger.info(f"_output_handler_payment {block_dto.bid} {outline_item_info.bid}")
    content: PaymentDTO = block_dto.block_content
    order = init_buy_record(app, user_info.user_id, outline_item_info.shifu_bid)
    if order.status != BUY_STATUS_SUCCESS:
        title = content.label
        title = get_script_ui_label(app, title)
        if not title:
            title = _("COMMON.CHECKOUT")
        btn = [{"label": title, "value": order.order_id}]
        yield make_script_dto(
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
        yield make_script_dto(
            "buttons",
            {"buttons": btn},
            outline_item_info.bid,
            block_dto.bid,
        )
