from flaskr.api.llm import invoke_llm
from flaskr.api.langfuse import langfuse_client
from flaskr.service.study.utils import get_model_setting
from flaskr.service.study.utils import extract_variables
from flaskr.service.shifu.block_funcs import (
    get_block_by_id,
    get_system_block_by_outline_id,
)
from langchain.prompts import PromptTemplate
from flaskr.service.common import raise_error
from flaskr.service.study.dtos import ScriptDTO
from flaskr.service.study.utils import make_script_dto_to_stream
from flaskr.service.lesson.const import STATUS_PUBLISH, STATUS_DRAFT


def format_script_prompt(script_prompt: str, script_variables: dict) -> str:
    prompt_template_lc = PromptTemplate.from_template(script_prompt)
    keys = extract_variables(script_prompt)
    fmt_keys = {}
    for key in keys:
        if key in script_variables:
            fmt_keys[key] = script_variables[key]
        else:
            fmt_keys[key] = "目前未知"
    return prompt_template_lc.format(**fmt_keys)


def get_system_prompt(app, block_id):
    with app.app_context():
        block_info = get_block_by_id(app, block_id)
        if not block_info:
            raise_error("SCENARIO.BLOCK_NOT_FOUND")
        block_info = get_system_block_by_outline_id(app, block_info.lesson_id)
        if not block_info:
            return ""
    return block_info.script_prompt


def debug_script(
    app,
    user_id,
    block_id,
    block_prompt,
    block_system_prompt,
    block_model,
    block_temperature,
    block_variables,
    block_other_conf,
):

    with app.app_context():

        try:
            block_info = get_block_by_id(app, block_id)
            if not block_info:
                raise_error("SCENARIO.BLOCK_NOT_FOUND")
            trace_args = {}
            trace_args["user_id"] = user_id
            trace_args["session_id"] = "debug-" + block_id
            trace_args["input"] = block_prompt
            trace_args["name"] = "debug"
            trace = langfuse_client.trace(**trace_args)
            app.logger.info(f"debug_script {block_id} ")
            model_setting = get_model_setting(
                app, block_info, [STATUS_PUBLISH, STATUS_DRAFT]
            )
            app.logger.info(f"model_setting: {model_setting}")
            app.logger.info(f"block_model: {block_model}")
            app.logger.info(f"block_temperature: {block_temperature}")
            app.logger.info(f"block_variables: {block_variables}")
            app.logger.info(f"block_other_conf: {block_other_conf}")
            if not block_model or not block_model.strip():
                block_model = model_setting.model_name
            if block_temperature is None:
                block_temperature = model_setting.model_args.get("temperature", 0.8)
            if block_variables:
                block_prompt = format_script_prompt(block_prompt, block_variables)
            if block_system_prompt and block_system_prompt.strip():
                system_prompt = format_script_prompt(
                    block_system_prompt, block_variables
                )
            else:
                system_prompt = None

            span = trace.span(name="debug_script", input=block_prompt)
            response_text = ""
            response = invoke_llm(
                app,
                user_id,
                span,
                block_model,
                block_prompt,
                system=system_prompt,
                **{"temperature": block_temperature},
                generation_name="debug-" + block_id,
            )
            for chunk in response:
                response_text += chunk.result
                yield make_script_dto_to_stream(
                    ScriptDTO(
                        "text", chunk.result, block_info.lesson_id, block_id, trace.id
                    )
                )
            yield make_script_dto_to_stream(
                ScriptDTO("text_end", "", block_info.lesson_id, block_id, trace.id)
            )
            span.update(output=response_text)
            trace.end()
        except Exception as e:
            app.logger.error(f"debug_script {block_id} error: {e}")
