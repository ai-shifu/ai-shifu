from flask import Flask

from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.api.llm import invoke_llm
from flaskr.api.check import (
    check_text,
    CHECK_RESULT_PASS,
    CHECK_RESULT_REJECT,
)
from flaskr.service.check_risk import add_risk_control_result
from flaskr.service.learn.const import (
    ROLE_TEACHER,
)
from flaskr.dao import db
from flaskr.service.user.models import User
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.learn.utils_v2 import init_generated_block
from flaskr.service.shifu.consts import BLOCK_TYPE_MDINTERACTION_VALUE


class BreakException(Exception):
    pass


def check_text_with_llm_response(
    app: Flask,
    user_info: User,
    log_script: LearnGeneratedBlock,
    input: str,
    span,
    outline_item_bid: str,
    shifu_bid: str,
    block_position: int,
    llm_settings: LLMSettings,
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

    if res.check_result == CHECK_RESULT_REJECT:
        labels = res.risk_labels
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
            model=llm_settings.model,
            json=False,
            stream=True,
            generation_name="check_text_reject_"
            + block_position
            + "_"
            + "_"
            + str(outline_item_bid),
            **{"temperature": llm_settings.temperature},
        )
        response_text = ""

        for i in res:
            yield i.result
            response_text += i.result
        log_script = init_generated_block(
            app,
            shifu_bid,
            outline_item_bid,
            attend_id,
            user_info.user_id,
            BLOCK_TYPE_MDINTERACTION_VALUE,
            "",
            block_position,
        )
        log_script.generated_content = response_text
        log_script.role = ROLE_TEACHER
        db.session.add(log_script)
        db.session.flush()

    else:
        app.logger.info(f"check_text_by_{res.provider} is None")
        # For generator functions, we need to yield a special marker to indicate None
        # and then return to stop the generator
        yield None
        return
