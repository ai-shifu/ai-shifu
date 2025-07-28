from flask import Flask
from flaskr.service.shifu.adapter import BlockDTO, ContentDTO
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.study.plugin import register_shifu_output_handler
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.study.utils import make_script_dto
from flaskr.service.user.models import User
from langfuse.client import StatefulTraceClient
import time


@register_shifu_output_handler("content")
def handle_output_content(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
) -> ScriptDTO:
    content_dto: ContentDTO = block_dto.block_content
    prompt = content_dto.content
    for i in prompt:
        msg = make_script_dto("text", i, block_dto.bid, outline_item_info.bid)
        yield msg
        time.sleep(0.01)

    yield make_script_dto(
        "text_end",
        script_content="",
        script_id=block_dto.bid,
        lesson_id=outline_item_info.bid,
        log_id="",
    )
