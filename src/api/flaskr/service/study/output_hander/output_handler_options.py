from flask import Flask
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO, OptionsDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.study.plugin import register_shifu_output_handler
from flaskr.service.study.utils import make_script_dto, get_script_ui_label
import json


@register_shifu_output_handler("options")
def _output_handler_options(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    app.logger.info(f"_output_handler_options {block_dto.bid} {outline_item_info.bid}")
    options: OptionsDTO = block_dto.options
    if not options:
        return
    options_list = options.options
    if not options_list:
        return
    options = []
    for option in options_list:
        option["label"] = get_script_ui_label(app, option.label)
        option["value"] = option.value
        options.append(option)
    yield make_script_dto("options", json.dumps({"options": options}))
