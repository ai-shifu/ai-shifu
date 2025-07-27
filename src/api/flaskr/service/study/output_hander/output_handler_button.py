from flask import Flask
from flaskr.service.shifu.adapter import BlockDTO, ButtonDTO
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from langfuse.client import StatefulTraceClient
from flaskr.service.user.models import User
from flaskr.service.study.utils import get_script_ui_label, make_script_dto
from flaskr.service.study.const import INPUT_TYPE_CONTINUE
from flaskr.i18n import _


def _output_handler_button(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    button_dto: ButtonDTO = block_dto.button

    display = bool(button_dto.label)  # Set display based on whether msg has content
    app.logger.info("handle_input_button:{}".format(button_dto.label))
    # if is json
    msg = get_script_ui_label(app, button_dto.label)
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

    return make_script_dto(
        "buttons",
        {"buttons": btn},
        outline_item_info.bid,
        block_dto.bid,
    )
