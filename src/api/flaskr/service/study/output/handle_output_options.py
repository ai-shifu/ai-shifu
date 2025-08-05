from flask import Flask
from flaskr.service.study.const import INPUT_TYPE_SELECT
from flaskr.service.study.plugin import register_shifu_output_handler
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.user.models import User
from flaskr.service.study.utils import get_script_ui_label
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO, OptionsDTO
from langfuse.client import StatefulTraceClient


@register_shifu_output_handler("options")
def _handle_output_options(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
) -> ScriptDTO:
    selection: OptionsDTO = block_dto.block_content
    btns = []
    for option in selection.options:
        label = get_script_ui_label(app, option.label)
        if label == "":
            label = option.value
        btn = {
            "label": label,
            "value": label,
            "type": INPUT_TYPE_SELECT,
        }
        btns.append(btn)
    return ScriptDTO(
        "buttons",
        {"buttons": btns},
        outline_item_info.bid,
        block_dto.bid,
    )
