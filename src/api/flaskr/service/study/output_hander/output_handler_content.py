from flask import Flask
from flaskr.service.shifu.adapter import BlockDTO, ContentDTO
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from langfuse.client import StatefulTraceClient
from flaskr.service.user.models import User
from flaskr.service.study.plugin import register_shifu_output_handler
from flaskr.service.study.utils import make_script_dto, get_fmt_prompt


@register_shifu_output_handler("content")
def _output_handler_content(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    app.logger.info(f"_output_handler_content {block_dto.bid} {outline_item_info.bid}")
    content_dto: ContentDTO = block_dto.content
    prompt = get_fmt_prompt(
        app,
        user_info.user_id,
        outline_item_info.shifu_bid,
        content_dto.content,
    )
    if not prompt:
        prompt = content_dto.content
    if content_dto.llm_enabled:

        for text in content_dto.text:
            yield make_script_dto(
                "text",
                text,
                outline_item_info.bid,
                block_dto.bid,
            )
        yield make_script_dto(
            "text_end",
            "",
            outline_item_info.bid,
            block_dto.bid,
        )

    else:
        pass

    return make_script_dto(
        "content",
        content_dto.content,
        outline_item_info.bid,
        block_dto.bid,
    )
