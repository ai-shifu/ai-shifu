from flask import Flask
from flaskr.service.shifu.adapter import BlockDTO, ContentDTO
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.study.plugin import register_shifu_output_handler
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.study.utils import make_script_dto
from flaskr.service.user.models import User
from langfuse.client import StatefulTraceClient
import time
from flaskr.service.study.utils import get_fmt_prompt
from flaskr.service.study.const import ROLE_TEACHER
from flaskr.service.study.utils import generation_attend
from flaskr.service.study.context import LLMSettings, RunScriptContext
from flaskr.api.llm import invoke_llm
from flaskr.dao import db
from typing import Generator


@register_shifu_output_handler("content")
def handle_output_content(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
) -> Generator[ScriptDTO, None, None]:
    content_dto: ContentDTO = block_dto.block_content
    content = content_dto.content
    prompt = get_fmt_prompt(
        app, user_info.user_id, outline_item_info.shifu_bid, profile_tmplate=content
    )
    log_script = generation_attend(
        app, user_info, attend_id, outline_item_info, block_dto
    )
    log_script.script_content = prompt
    log_script.script_role = ROLE_TEACHER
    text = ""
    if not content_dto.llm_enabled:
        span = trace.span(name="prompt_sript")
        for i in prompt:
            msg = make_script_dto(
                "text", i, block_dto.bid, outline_item_info.bid, log_script.log_id
            )
            yield msg
            time.sleep(0.01)

        trace_args["output"] = trace_args["output"] + "\r\n" + prompt
        trace.update(**trace_args)
        text = prompt
    else:
        context = RunScriptContext.get_current_context(app)
        # get model setting
        span = trace.span(name="prompt_sript")
        model_setting: LLMSettings = None
        if content_dto.llm:
            model_setting = LLMSettings(
                model=content_dto.llm,
                temperature=content_dto.llm_temperature,
            )
        else:
            model_setting = context.get_llm_settings(outline_item_info)

        system_prompt_template = context.get_system_prompt(outline_item_info)
        system_prompt = (
            None
            if system_prompt_template is None or system_prompt_template == ""
            else get_fmt_prompt(
                app,
                user_info.user_id,
                outline_item_info.shifu_bid,
                system_prompt_template,
            )
        )
        prompt = get_fmt_prompt(
            app,
            user_info.user_id,
            outline_item_info.shifu_bid,
            content_dto.content,
        )
        resp = invoke_llm(
            app,
            user_info.user_id,
            span,
            model=model_setting.model,
            stream=True,
            system=system_prompt,
            generation_name=outline_item_info.position
            + "_"
            + str(block_dto.bid)
            + "_"
            + str(outline_item_info.bid),
            temperature=model_setting.temperature,
            message=prompt,
        )
        response_text = ""
        for chunk in resp:
            current_content = chunk.result
            if isinstance(current_content, str):
                response_text += current_content
                yield make_script_dto(
                    "text",
                    current_content,
                    block_dto.bid,
                    outline_item_info.bid,
                    log_script.log_id,
                )
        trace_args["output"] = trace_args["output"] + "\r\n" + response_text
        trace.update(**trace_args)
        text = response_text
    yield make_script_dto(
        "text_end", "", block_dto.bid, outline_item_info.bid, log_script.log_id
    )
    log_script.script_content = text
    db.session.add(log_script)
    db.session.flush()
