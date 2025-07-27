from flask import Flask
from flaskr.service.shifu.adapter import BlockDTO, LoginDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.study.utils import get_script_ui_label, make_script_dto
from flaskr.service.study.const import INPUT_TYPE_REQUIRE_LOGIN
from flaskr.service.study.plugin import register_shifu_input_handler
from flaskr.i18n import _
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto


@register_shifu_input_handler("login")
def _input_handler_login(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    login_dto: LoginDTO = block_dto.block_content
    title = get_script_ui_label(app, login_dto.label)
    if not title:
        title = _("COMMON.LOGIN")
    btn = [
        {
            "label": title,
            "value": title,
            "type": INPUT_TYPE_REQUIRE_LOGIN,
        }
    ]
    app.logger.info(
        f"_input_handler_login {block_dto.bid} {outline_item_info.bid} {title} {btn}"
    )
    yield make_script_dto(
        INPUT_TYPE_REQUIRE_LOGIN,
        {"buttons": btn},
        block_dto.bid,
        block_dto.bid,
    )
