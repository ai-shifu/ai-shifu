from flask import Flask

from flaskr.service.order.consts import (
    ATTEND_STATUS_BRANCH,
    ATTEND_STATUS_IN_PROGRESS,
    ATTEND_STATUS_RESET,
)
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.plugin import register_shifu_output_handler
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.study.const import INPUT_TYPE_BRANCH
from flaskr.dao import db
from flaskr.service.user.models import User
from flaskr.util.uuid import generate_id
from flaskr.service.study.utils import get_script_ui_label
from flaskr.i18n import _
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from flaskr.service.shifu.dtos import GotoDTO, GotoConditionDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.profile.funcs import get_user_variable_by_variable_id


@register_shifu_output_handler("goto")
def _handle_output_goto(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
) -> ScriptDTO:

    app.logger.info(f"goto: {block_dto.block_content}")
    goto: GotoDTO = block_dto.block_content
    variable_id = block_dto.variable_bids[0] if block_dto.variable_bids else ""
    if not variable_id:
        return None
    user_variable = get_user_variable_by_variable_id(
        app, user_info.user_id, variable_id
    )

    if not user_variable:
        return None
    destination_condition: GotoConditionDTO = None
    for condition in goto.conditions:
        if condition.value == user_variable:
            destination_condition = condition
            break
    if not destination_condition:
        return None

    app.logger.info(
        f"user_variable: {user_variable} find destination {destination_condition.destination_bid}"
    )
    goto_attend = AICourseLessonAttend.query.filter(
        AICourseLessonAttend.user_id == user_info.user_id,
        AICourseLessonAttend.course_id == outline_item_info.shifu_bid,
        AICourseLessonAttend.lesson_id == destination_condition.destination_bid,
        AICourseLessonAttend.status != ATTEND_STATUS_RESET,
    ).first()
    if not goto_attend:
        goto_attend = AICourseLessonAttend()
        goto_attend.user_id = user_info.user_id
        goto_attend.course_id = outline_item_info.shifu_bid
        goto_attend.lesson_id = destination_condition.destination_bid
        goto_attend.attend_id = generate_id(app)
        goto_attend.status = ATTEND_STATUS_IN_PROGRESS
        goto_attend.script_index = 0
        db.session.add(goto_attend)
        db.session.flush()

    msg = get_script_ui_label(app, block_dto.block_content)
    from flaskr.service.study.context import RunScriptContext

    context = RunScriptContext.get_current_context(app)
    if context:
        context._current_attend = goto_attend
        context._current_outline_item = outline_item_info
        context._current_attend.status = ATTEND_STATUS_BRANCH
        db.session.flush()
    if not msg:
        msg = _("COMMON.CONTINUE")
    btn = [
        {
            "label": msg,
            "value": block_dto.block_content,
            "type": INPUT_TYPE_BRANCH,
        }
    ]
    return ScriptDTO(
        "buttons",
        {"buttons": btn},
        outline_item_info.bid,
        outline_item_info.bid,
    )
