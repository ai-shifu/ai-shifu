import time

from flask import Flask

from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.api.llm import invoke_llm
from flaskr.api.check import (
    check_text,
    CHECK_RESULT_PASS,
    CHECK_RESULT_REJECT,
)
from flaskr.service.learn.utils import generation_attend
from flaskr.service.check_risk import add_risk_control_result
from flaskr.service.learn.const import (
    ROLE_TEACHER,
)
from flaskr.dao import db
from flaskr.service.learn.utils import make_script_dto
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from flaskr.service.learn.context import RunScriptContext
from flaskr.service.user.models import User


class BreakException(Exception):
    pass


def check_text_with_llm_response(
    app: Flask,
    user_info: User,
    log_script: LearnGeneratedBlock,
    input: str,
    span,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    attend_id: str,
    fmt_prompt: str,
):
    res = check_text(app, log_script.generated_block_bid, input, user_info.user_id)
    span.event(name="check_text", input=input, output=res)
    add_risk_control_result(
        app,
        log_script.generated_block_bid,
        user_info.user_id,
        input,
        res.provider,
        res.check_result,
        str(res.raw_data),
        1 if res.check_result == CHECK_RESULT_PASS else 0,
        "check_text",
    )
    context = RunScriptContext.get_current_context(app)

    if res.check_result == CHECK_RESULT_REJECT:
        labels = res.risk_labels
        model_setting = context.get_llm_settings(outline_item_info)
        prompt = f"""# 角色
你是一名在线老师，正在和学生对话

# 任务
学生的发言有不合法不合规的地方，请指出问题，并把教学拉回到正常轨道

# 当前教学内容
{fmt_prompt}

# 学生发言
{input}

# 学生发言违规原因
{", ".join(labels)}
"""
        res = invoke_llm(
            app,
            user_info.user_id,
            span,
            message=prompt,
            model=model_setting.model,
            json=False,
            stream=True,
            generation_name="check_text_reject_"
            + outline_item_info.position
            + "_"
            + str(block_dto.bid)
            + "_"
            + str(outline_item_info.bid),
            **{"temperature": model_setting.temperature},
        )
        response_text = ""

        for i in res:
            yield make_script_dto(
                "text", i.result, log_script.block_bid, log_script.outline_item_bid
            )
            response_text += i.result
            time.sleep(0.01)

        log_script = generation_attend(
            app, user_info, attend_id, outline_item_info, block_dto
        )
        log_script.generated_content = response_text
        log_script.role = ROLE_TEACHER
        db.session.add(log_script)
        db.session.flush()
        yield make_script_dto(
            "text_end",
            "",
            log_script.block_bid,
            log_script.outline_item_bid,
            log_script.generated_block_bid,
        )
    else:
        app.logger.info(f"check_text_by_{res.provider} is None")
        return
