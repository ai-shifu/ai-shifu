from flask import Flask
from flaskr.service.user.models import User
from flaskr.service.study.dtos import ScriptDTO
from flaskr.framework.plugin.plugin_manager import extensible
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.dtos import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.study.utils import get_follow_up_info
from flaskr.service.shifu.consts import ASK_MODE_ENABLE


@extensible
def _handle_output_ask(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
) -> ScriptDTO:

    shifu_bid = outline_item_info.shifu_bid
    app.logger.info(f"block_dto: {shifu_bid}")
    follow_up_info = get_follow_up_info(
        app, outline_item_info.shifu_bid, block_dto, attend_id
    )

    ask_mode = follow_up_info.ask_mode
    visible = True if ask_mode == ASK_MODE_ENABLE else False
    enable = True if ask_mode == ASK_MODE_ENABLE else False
    return ScriptDTO(
        "ask_mode",
        {"ask_mode": enable, "visible": visible, "ask_limit_count": 9999},
        outline_item_info.bid,
        block_dto.bid,
    )
