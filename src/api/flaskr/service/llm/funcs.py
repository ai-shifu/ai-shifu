from flaskr.api.llm import invoke_llm
from flaskr.api.langfuse import langfuse_client
from flaskr.service.study.utils import get_script_by_id, get_model_setting
from flaskr.service.study.utils import extract_variables

from langchain.prompts import PromptTemplate


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


def debug_script(
    app,
    user_id,
    script_id,
    script_prompt,
    script_model,
    script_temprature,
    script_variables,
    script_other_conf,
):

    with app.app_context():
        trace_args = {}
        trace_args["user_id"] = user_id
        trace_args["session_id"] = "debug-" + script_id
        trace_args["input"] = ""
        trace_args["name"] = "ai-python"
        trace = langfuse_client.trace(**trace_args)
        app.logger.info(f"debug_script {script_id} ")
        try:
            if not script_model or not script_model.strip():
                script_info = get_script_by_id(app, script_id)
                model_setting = get_model_setting(app, script_info)
                script_model = model_setting.model_name
            if script_variables:
                script_prompt = format_script_prompt(script_prompt, script_variables)
            span = trace.span(name="debug_script", input=script_prompt)
            response = invoke_llm(
                app,
                user_id,
                span,
                script_model,
                script_prompt,
                **{"temperature": script_temprature},
                generation_name="debug-" + script_id,
            )
            for chunk in response:
                yield f"""data: {{"text":"{chunk.result}"}}\n\n"""
        except Exception as e:
            trace.error(e)
            raise e
        finally:
            trace.end()
    pass
