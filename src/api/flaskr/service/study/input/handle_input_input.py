import time
from flask import Flask
from flaskr.api.llm import invoke_llm
from flaskr.service.profile.funcs import save_user_profiles
from flaskr.service.study.input_funcs import (
    BreakException,
    check_text_with_llm_response,
)
from flaskr.service.study.const import ROLE_STUDENT, ROLE_TEACHER
from flaskr.service.study.plugin import (
    register_shifu_input_handler,
)
from flaskr.service.study.utils import (
    extract_json_from_markdown,
    generation_attend,
    get_fmt_prompt,
    make_script_dto,
    get_script_ui_label,
)
from flaskr.dao import db
from flaskr.framework.plugin.plugin_manager import extensible_generic
import json
from flaskr.service.study.output.handle_output_input import _handle_output_input
from flaskr.service.user.models import User
from flaskr.service.profile.models import ProfileItem
from langfuse.client import StatefulTraceClient
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from flaskr.service.shifu.dtos import InputDTO
from flaskr.service.study.context import LLMSettings, RunScriptContext


def safe_get_temperature(app: Flask, profile_item: ProfileItem):
    try:
        return float(profile_item.profile_prompt_model_args)
    except Exception as e:
        app.logger.error(f"safe_get_temperature error: {e}")
        return 0.3


@register_shifu_input_handler("input")
@extensible_generic
def _handle_input_input(
    app: Flask,
    user_info: User,
    attend_id: str,
    input: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    trace_args: dict,
    trace: StatefulTraceClient,
):
    model_setting = None
    check_prompt_template = None
    inputDto: InputDTO = block_dto.block_content
    app.logger.info(f"inputDto: {inputDto.__json__()}")
    context = RunScriptContext.get_current_context(app)

    if inputDto.llm:
        model_setting = LLMSettings(
            model=inputDto.llm,
            temperature=inputDto.llm_temperature,
        )

    if (
        inputDto.result_variable_bids is not None
        and len(inputDto.result_variable_bids) > 0
    ):
        profile_item = (
            ProfileItem.query.filter(
                ProfileItem.profile_id.in_(inputDto.result_variable_bids)
            )
            .order_by(ProfileItem.id.desc())
            .first()
        )
        if (
            profile_item
            and profile_item.profile_prompt_model
            and profile_item.profile_prompt_model.strip()
        ):
            model_setting = LLMSettings(
                model=profile_item.profile_prompt_model,
                temperature=safe_get_temperature(app, profile_item),
            )
            check_prompt_template = profile_item.profile_prompt

    if model_setting is None:
        model_setting = context.get_llm_settings(outline_item_info)

    app.logger.info(f"model_setting: {model_setting.__json__()}")

    # get content prompt to generate content if check failed
    content_prompt_template = inputDto.prompt
    if content_prompt_template is not None and content_prompt_template != "":
        content_prompt = get_fmt_prompt(
            app,
            user_info.user_id,
            outline_item_info.shifu_bid,
            content_prompt_template,
            input,
        )
    else:
        content_prompt = ""

    log_script = generation_attend(
        app, user_info, attend_id, outline_item_info, block_dto
    )
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT
    log_script.script_ui_conf = json.dumps(
        _handle_output_input(
            app, user_info, attend_id, outline_item_info, block_dto, trace, trace_args
        ).__json__()
    )
    db.session.add(log_script)
    span = trace.span(name="user_input", input=input)

    res = check_text_with_llm_response(
        app,
        user_info,
        log_script,
        input,
        span,
        outline_item_info,
        block_dto,
        attend_id,
        content_prompt,
    )
    try:
        first_value = next(res)
        yield first_value
        yield from res
        db.session.flush()
        raise BreakException
    except StopIteration:
        app.logger.info("check_text_by_edun is None ,invoke_llm")

    # get system prompt to generate content
    system_prompt_template = context.get_system_prompt(outline_item_info)
    system_prompt = (
        None
        if system_prompt_template is None or system_prompt_template == ""
        else get_fmt_prompt(
            app, user_info.user_id, outline_item_info.shifu_bid, system_prompt_template
        )
    )

    # get check prompt to extract profile
    if check_prompt_template is None or check_prompt_template == "":
        check_prompt_template = inputDto.prompt

    check_prompt = get_fmt_prompt(
        app,
        user_info.user_id,
        outline_item_info.shifu_bid,
        check_prompt_template,
        input,
    )
    resp = invoke_llm(
        app,
        user_info.user_id,
        span,
        model=model_setting.model,
        json=True,
        stream=True,
        system=system_prompt,
        message=check_prompt,
        generation_name="user_input_"
        + outline_item_info.position
        + "_"
        + str(outline_item_info.position)
        + "_",
        temperature=model_setting.temperature,
    )
    response_text = ""
    check_success = False
    for i in resp:
        current_content = i.result
        if isinstance(current_content, str):
            response_text += current_content

    jsonObj = extract_json_from_markdown(app, response_text)

    check_success = jsonObj.get("result", "") == "ok"
    if check_success:
        app.logger.info("check success")
        profile_tosave = jsonObj.get("parse_vars")
        save_user_profiles(
            app, user_info.user_id, outline_item_info.shifu_bid, profile_tosave
        )
        for key in profile_tosave:
            yield make_script_dto(
                "profile_update",
                {"key": key, "value": profile_tosave[key]},
                outline_item_info.bid,
                outline_item_info.bid,
            )
            time.sleep(0.01)
        span.end()
        db.session.flush()

    else:
        reason = jsonObj.get("reason", response_text)
        for text in reason:
            yield make_script_dto(
                "text", text, outline_item_info.bid, outline_item_info.bid
            )
            time.sleep(0.01)
        log_script = generation_attend(
            app, user_info, attend_id, outline_item_info, block_dto
        )
        log_script.script_content = reason
        log_script.script_role = ROLE_TEACHER
        db.session.add(log_script)
        span.end(output=response_text)
        trace_args["output"] = trace_args["output"] + "\r\n" + response_text
        trace.update(**trace_args)
        db.session.flush()
        yield make_script_dto(
            "text_end",
            "",
            outline_item_info.bid,
            outline_item_info.bid,
            log_script.log_id,
        )
        yield make_script_dto(
            "sys_user_input",
            get_script_ui_label(app, inputDto.placeholder),
            outline_item_info.bid,
            outline_item_info.bid,
        )
        raise BreakException
