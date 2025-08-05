import time
from typing import Generator
from flask import Flask
from flaskr.service.common.models import AppException
from flaskr.service.study.const import INPUT_TYPE_CHECKCODE, ROLE_TEACHER
from flaskr.service.study.input_funcs import BreakException
from flaskr.service.study.plugin import (
    register_shifu_input_handler,
)
from flaskr.service.study.utils import (
    generation_attend,
    get_script_ui_label,
    make_script_dto,
)
from flaskr.service.user.common import verify_sms_code_without_phone
from flaskr.service.study.const import ROLE_STUDENT
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.user.models import User
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from flaskr.service.shifu.dtos import CheckCodeDTO
from langfuse.client import StatefulTraceClient


@register_shifu_input_handler("checkcode")
@extensible_generic
def _handle_input_checkcode(
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
    try:
        log_script = generation_attend(
            app, user_info, attend_id, outline_item_info, block_dto
        )
        log_script.script_content = input
        log_script.script_role = ROLE_STUDENT  # type: ignore
        db.session.add(log_script)
        course_id = outline_item_info.shifu_bid
        ret = verify_sms_code_without_phone(app, user_info, input, course_id)
        yield make_script_dto(
            "profile_update",
            {"key": "phone", "value": ret.userInfo.mobile},
            block_dto.bid,
        )
        yield make_script_dto(
            "user_login",
            {
                "phone": ret.userInfo.mobile,
                "user_id": ret.userInfo.user_id,
                "token": ret.token,
            },
            block_dto.bid,
        )
        input = None
        span = trace.span(name="user_input_phone", input=input)
        span.end()
    except AppException as e:
        for i in e.message:
            yield make_script_dto("text", i, block_dto.bid, outline_item_info.bid)
            time.sleep(0.01)
        yield make_script_dto("text_end", "", block_dto.bid, outline_item_info.bid)
        content: CheckCodeDTO = block_dto.block_content
        yield make_script_dto(
            INPUT_TYPE_CHECKCODE,
            get_script_ui_label(app, content.placeholder),
            block_dto.bid,
            outline_item_info.bid,
        )
        log_script = generation_attend(
            app, user_info, attend_id, outline_item_info, block_dto
        )
        log_script.script_content = e.message
        log_script.script_role = ROLE_TEACHER
        db.session.add(log_script)
        raise BreakException
