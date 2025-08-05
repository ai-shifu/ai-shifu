from flask import Flask

from flaskr.service.study.plugin import register_shifu_output_handler
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.user.models import User
from flaskr.service.shifu.adapter import BlockDTO
from langfuse.client import StatefulTraceClient
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.order.models import AICourseBuyRecord
from flaskr.service.order.consts import BUY_STATUS_SUCCESS
from flaskr.service.common import raise_error
from flaskr.service.shifu.shifu_struct_manager import (
    get_shifu_dto,
    ShifuInfoDto,
    ShifuOutlineItemDto,
    get_shifu_struct,
)
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.order.consts import ATTEND_STATUS_RESET
from flaskr.service.study.plugin import SHIFU_OUTPUT_HANDLER_MAP


@register_shifu_output_handler("goto")
def _handle_output_goto(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
    is_preview: bool = False,
) -> ScriptDTO:
    from flaskr.service.study.context import RunScriptContext

    run_script_context = RunScriptContext.get_current_context(app)
    if not run_script_context:
        shifu_info: ShifuInfoDto = get_shifu_dto(
            app, outline_item_info.shifu_bid, is_preview
        )
        struct_info: HistoryItem = None
        struct_info = get_shifu_struct(app, shifu_info.bid, is_preview)
        if not struct_info:
            raise_error("LESSON.SHIFU_NOT_FOUND")

        if shifu_info.price > 0:
            success_buy_record = (
                AICourseBuyRecord.query.filter(
                    AICourseBuyRecord.user_id == user_info.user_id,
                    AICourseBuyRecord.course_id == shifu_info.bid,
                    AICourseBuyRecord.status == BUY_STATUS_SUCCESS,
                )
                .order_by(AICourseBuyRecord.id.desc())
                .first()
            )
            if not success_buy_record:
                is_paid = False
            else:
                is_paid = True
        else:
            is_paid = True

        run_script_context: RunScriptContext = RunScriptContext(
            app=app,
            shifu_info=shifu_info,
            struct=struct_info,
            outline_item_info=outline_item_info,
            user_info=user_info,
            is_paid=is_paid,
            preview_mode=is_preview,
        )
    attend = AICourseLessonAttend.query.filter(
        AICourseLessonAttend.user_id == user_info.user_id,
        AICourseLessonAttend.course_id == shifu_info.bid,
        AICourseLessonAttend.lesson_id == outline_item_info.bid,
        AICourseLessonAttend.status != ATTEND_STATUS_RESET,
    ).first()
    run_script_info = run_script_context._get_run_script_info(attend)
    return SHIFU_OUTPUT_HANDLER_MAP[run_script_info.block_dto.type](
        app,
        user_info,
        attend_id,
        outline_item_info,
        run_script_info.block_dto,
        trace_args,
        trace,
        is_preview,
    )
