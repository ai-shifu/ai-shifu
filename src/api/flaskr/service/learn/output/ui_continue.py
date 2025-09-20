from flask import Flask

from flaskr.service.learn.const import INPUT_TYPE_CONTINUE
from flaskr.service.learn.dtos import ScriptDTO
from flaskr.service.user.models import User
from flaskr.i18n import _
from flaskr.service.learn.utils import get_script_ui_label
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.shifu.dtos import ButtonDTO


def make_continue_ui(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
) -> ScriptDTO:
    button = block_dto.block_content
    msg = ""
    if isinstance(button, ButtonDTO):
        msg = get_script_ui_label(app, button.label)

    display = bool(msg)
    if not msg:
        msg = _("COMMON.CONTINUE")
    btn = [
        {
            "label": msg,
            "value": msg,
            "type": INPUT_TYPE_CONTINUE,
            "display": display,
        }
    ]

    return ScriptDTO(
        "buttons",
        {"buttons": btn},
        outline_item_info.bid,
        outline_item_info.bid,
    )
