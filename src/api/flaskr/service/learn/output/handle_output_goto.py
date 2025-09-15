from flask import Flask

from flaskr.service.learn.plugin import register_shifu_output_handler
from flaskr.service.learn.dtos import ScriptDTO
from flaskr.service.user.models import User
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.order.models import Order
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.common import raise_error
from flaskr.service.shifu.shifu_struct_manager import (
    get_shifu_dto,
    ShifuInfoDto,
    ShifuOutlineItemDto,
    get_shifu_struct,
)
from flaskr.service.learn.models import LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_RESET
from flaskr.service.learn.plugin import SHIFU_OUTPUT_HANDLER_MAP


@register_shifu_output_handler("goto")
def _handle_output_goto(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
) -> ScriptDTO:
    from flaskr.service.learn.context import RunScriptContext

    with app.app_context():
        run_script_context = RunScriptContext.get_current_context(app)
        if not run_script_context:
            shifu_info: ShifuInfoDto = get_shifu_dto(
                app, outline_item_info.shifu_bid, is_preview
            )
            struct_info = get_shifu_struct(app, shifu_info.bid, is_preview)
            if not struct_info:
                raise_error("LESSON.SHIFU_NOT_FOUND")

            if shifu_info.price > 0:
                success_buy_record = (
                    Order.query.filter(
                        Order.user_bid == user_info.user_id,
                        Order.shifu_bid == shifu_info.bid,
                        Order.status == ORDER_STATUS_SUCCESS,
                    )
                    .order_by(Order.id.desc())
                    .first()
                )
                if not success_buy_record:
                    is_paid = False
                else:
                    is_paid = True
            else:
                is_paid = True

            run_script_context: RunScriptContext = RunScriptContext(
                app=app,
                shifu_info=shifu_info,
                struct=struct_info,
                outline_item_info=outline_item_info,
                user_info=user_info,
                is_paid=is_paid,
                preview_mode=is_preview,
            )
        attend = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_info.user_id,
            LearnProgressRecord.shifu_bid == outline_item_info.shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_item_info.bid,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        ).first()

        run_script_info = run_script_context._get_run_script_info(attend)
        return SHIFU_OUTPUT_HANDLER_MAP[run_script_info.block_dto.type](
            app,
            user_info,
            attend_id,
            outline_item_info,
            run_script_info.block_dto,
            trace_args,
            trace,
            is_preview,
        )
