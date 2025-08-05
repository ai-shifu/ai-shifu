from flask import Flask
from flaskr.service.study.plugin import (
    register_shifu_continue_handler,
)
from flaskr.service.order.models import AICourseBuyRecord
from flaskr.service.order.consts import BUY_STATUS_SUCCESS
from flaskr.service.common import raise_error
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from typing import Generator


# geyunfei
#
@register_shifu_continue_handler("payment")
@extensible_generic
def _handle_input_continue_order(
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
    course_id = outline_item_info.shifu_bid
    buy_record = AICourseBuyRecord.query.filter(
        AICourseBuyRecord.course_id == course_id,
        AICourseBuyRecord.user_id == user_info.user_id,
        AICourseBuyRecord.status == BUY_STATUS_SUCCESS,
    ).first()
    if not buy_record:
        raise_error("COURSE.COURSE_NOT_PURCHASED")
    return None
