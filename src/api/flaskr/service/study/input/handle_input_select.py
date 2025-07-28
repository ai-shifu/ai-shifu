import json
from flask import Flask
from flaskr.service.profile.funcs import save_user_profiles
from flaskr.service.study.const import ROLE_STUDENT
from flaskr.service.study.plugin import (
    register_shifu_input_handler,
)
from flaskr.service.study.utils import generation_attend
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.study.output.options import _handle_output_options
from flaskr.service.user.models import User
from langfuse.client import StatefulTraceClient
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO, OptionsDTO
from flaskr.service.profile.funcs import get_profile_item_definition_list


@register_shifu_input_handler("options")
@register_shifu_input_handler("select")
@extensible_generic
def _handle_input_options(
    app: Flask,
    user_info: User,
    attend_id: str,
    input: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):

    options: OptionsDTO = block_dto.block_content
    result_variable_id = options.result_variable_bid

    profile_list = get_profile_item_definition_list(app, outline_item_info.shifu_bid)
    profile_to_save = {}
    for profile in profile_list:
        if profile.profile_id == result_variable_id:
            profile_to_save[profile.profile_key] = input
            break
    save_user_profiles(
        app, user_info.user_id, outline_item_info.shifu_bid, profile_to_save
    )
    log_script = generation_attend(
        app, user_info, attend_id, outline_item_info, block_dto
    )
    log_script.script_content = block_dto.block_content
    log_script.script_role = ROLE_STUDENT
    log_script.script_ui_conf = json.dumps(
        _handle_output_options(
            app, user_info, attend_id, outline_item_info, block_dto, trace_args, trace
        ).__json__()
    )
    db.session.add(log_script)
    span = trace.span(name="user_select", input=input)
    span.end()
    db.session.flush()
