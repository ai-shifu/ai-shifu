from flask import Flask
from flaskr.service.shifu.adapter import BlockDTO, LoginDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.study.utils import get_script_ui_label
from flaskr.service.study.const import INPUT_TYPE_REQUIRE_LOGIN
from flaskr.service.study.plugin import register_shifu_input_handler
from flaskr.service.study.dtos import ScriptDTO
from flaskr.i18n import _


@register_shifu_input_handler("login")
def handle_handler_login(
    app: Flask,
    user_id: str,
    attend_id: str,
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
        f"handle_handler_login {block_dto.bid} {block_dto.lesson_id} {title} {btn}"
    )
    return ScriptDTO(
        INPUT_TYPE_REQUIRE_LOGIN,
        {"buttons": btn},
        block_dto.bid,
        block_dto.bid,
    )
