from flask import Flask

from flaskr.service.study.const import INPUT_TYPE_REQUIRE_LOGIN
from flaskr.service.study.plugin import register_shifu_output_handler
from flaskr.service.user.models import User
from flaskr.i18n import _
from flaskr.service.study.utils import get_script_ui_label
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.shifu.dtos import LoginDTO
from flaskr.service.study.dtos import ScriptDTO


@register_shifu_output_handler("login")
def _handle_output_login(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
) -> ScriptDTO:
    login: LoginDTO = block_dto.block_content
    title = get_script_ui_label(app, login.label)
    if not title:
        title = _("COMMON.LOGIN")
    # display = bool(title)
    btn = [
        {
            "label": title,
            "value": title,
            "type": INPUT_TYPE_REQUIRE_LOGIN,
        }
    ]
    return ScriptDTO(
        INPUT_TYPE_REQUIRE_LOGIN,
        {"buttons": btn},
        outline_item_info.bid,
        block_dto.bid,
    )
