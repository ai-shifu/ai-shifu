import time
from flask import Flask
from flaskr.service.learn.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.learn.input_funcs import BreakException
from flaskr.service.learn.plugin import (
    register_shifu_input_handler,
)
from flaskr.service.learn.utils import (
    check_phone_number,
    generation_attend,
    make_script_dto,
)
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
from flaskr.service.user.models import User
from flaskr.service.learn.utils import get_script_ui_label
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.learn.const import INPUT_TYPE_PHONE
from typing import Generator
from flaskr.service.shifu.dtos import PhoneDTO


@register_shifu_input_handler("phone")
@extensible_generic
def _handle_input_phone(
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
    log_script = generation_attend(
        app, user_info, attend_id, outline_item_info, block_dto
    )
    log_script.generated_content = input
    log_script.role = ROLE_STUDENT  # type: ignore
    phone_input: PhoneDTO = block_dto.block_content
    db.session.add(log_script)
    span = trace.span(name="user_input_phone", input=input)
    response_text = "请输入正确的手机号"
    if not check_phone_number(app, user_info.user_id, phone_input.phone):
        for i in response_text:
            yield make_script_dto("text", i, block_dto.bid, outline_item_info.bid)
            time.sleep(0.01)
        yield make_script_dto("text_end", "", block_dto.bid, outline_item_info.bid)
        yield make_script_dto(
            INPUT_TYPE_PHONE,
            get_script_ui_label(app, phone_input.placeholder),
            block_dto.bid,
            outline_item_info.bid,
        )
        log_script = generation_attend(
            app, user_info, attend_id, outline_item_info, block_dto
        )
        log_script.generated_content = response_text
        log_script.role = ROLE_TEACHER
        db.session.add(log_script)
        span.end(output=response_text)
        db.session.flush()
        raise BreakException
    span.end()
