import json
from flask import Flask
from flaskr.service.profile.funcs import save_user_profiles
from flaskr.service.learn.const import ROLE_STUDENT
from flaskr.service.learn.plugin import (
    register_shifu_input_handler,
)
from flaskr.service.learn.utils import generation_attend
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.learn.output.handle_output_options import _handle_output_options
from flaskr.service.user.models import User
from langfuse.client import StatefulTraceClient
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO, OptionsDTO
from flaskr.service.profile.funcs import get_profile_item_definition_list
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.learn.output.handle_output_options import get_script_ui_label
from typing import Generator


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
    is_preview: bool = False,
) -> Generator[str, None, None]:
    options: OptionsDTO = block_dto.block_content
    result_variable_id = options.result_variable_bid

    profile_list = get_profile_item_definition_list(app, outline_item_info.shifu_bid)
    profile_to_save = []
    for profile in profile_list:
        if profile.profile_id == result_variable_id:
            for option in options.options:
                label = get_script_ui_label(app, option.label)
                if label == input:
                    profile_to_save.append(
                        ProfileToSave(
                            profile.profile_key, option.value, profile.profile_id
                        )
                    )
                    break

            break
    if profile_to_save:
        save_user_profiles(
            app, user_info.user_id, outline_item_info.shifu_bid, profile_to_save
        )
    else:
        app.logger.warning(f"profile_to_save is empty: {profile_to_save}")
    log_script = generation_attend(
        app, user_info, attend_id, outline_item_info, block_dto
    )
    log_script.generated_content = input
    log_script.role = ROLE_STUDENT
    log_script.block_content_conf = json.dumps(
        _handle_output_options(
            app,
            user_info,
            attend_id,
            outline_item_info,
            block_dto,
            trace,
            trace_args,
            is_preview,
        ).__json__()
    )
    db.session.add(log_script)
    span = trace.span(name="user_select", input=input)
    span.end()
    db.session.flush()
