from flask import Flask
from flaskr.service.user.models import User

# from flaskr.service.order.models import AICourseLessonAttend

# from flaskr.service.lesson.const import (
#     ASK_MODE_ENABLE,
# )

# from flaskr.service.study.utils import get_follow_up_info
from flaskr.service.study.dtos import ScriptDTO
from flaskr.framework.plugin.plugin_manager import extensible
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.dtos import BlockDTO
from langfuse.client import StatefulTraceClient

# from flaskr.service.study.context import RunScriptContext
# from flaskr.service.study.utils import get_fmt_prompt


@extensible
def _handle_output_ask(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    # from flaskr.service.study.context import RunScriptContext

    shifu_bid = outline_item_info.shifu_bid
    app.logger.info(f"block_dto: {shifu_bid}")

    # follow_up_info = get_follow_up_info(app, outline_item_info, attend)
    # ask_mode = follow_up_info.ask_mode
    # visible = True if ask_mode == ASK_MODE_ENABLE else False
    # enable = True if ask_mode == ASK_MODE_ENABLE else False
    # context = RunScriptContext.get_current_context(app)
    # app.logger.info(f"context: {context}")
    # system_prompt_template = context.get_system_prompt(outline_item_info)
    # system_prompt = get_fmt_prompt(
    #     app,
    #     user_info.user_id,
    #     outline_item_info.shifu_bid,
    #     system_prompt_template,
    # )
    return ScriptDTO(
        "ask_mode",
        {"ask_mode": True, "visible": True},
        outline_item_info.bid,
        block_dto.bid,
    )
