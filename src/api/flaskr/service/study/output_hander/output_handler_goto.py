from flask import Flask
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO, GotoDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.study.plugin import register_shifu_output_handler
from flaskr.service.study.utils import make_script_dto
from flaskr.service.study.const import INPUT_TYPE_BRANCH
from flaskr.service.study.i18n import _


@register_shifu_output_handler("goto")
def _output_handler_goto(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    app.logger.info(f"_output_handler_goto {block_dto.bid} {outline_item_info.bid}")
    goto: GotoDTO = block_dto.goto
    if not goto:
        return
    goto_list = goto.goto
    if not goto_list:
        return
    msg = _("COMMON.CONTINUE")
    btn = [
        {
            "label": msg,
            "type": INPUT_TYPE_BRANCH,
        }
    ]
    yield make_script_dto(
        "buttons",
        {"buttons": btn},
        block_dto.bid,
        outline_item_info.bid,
    )
