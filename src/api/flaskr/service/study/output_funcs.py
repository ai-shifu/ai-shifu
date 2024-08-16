


import json
import time
from trace import Trace
from flask import Flask

from flaskr.api.llm import invoke_llm
from flaskr.service.common.models import AppException
from flaskr.service.study.utils import  generation_attend, get_fmt_prompt

from ...service.lesson.models import AILessonScript
from ...service.order.models import AICourseLessonAttend
from ...service.study.const import INPUT_TYPE_LOGIN, ROLE_STUDENT, ROLE_TEACHER
from ...dao import db
from .utils import *



def generate_fix_output(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,trace:Trace,trace_args):
    prompt = ""
    if script_info.script_content_type == CONTENT_TYPE_IMAGE:
        prompt = "![img]({})".format(script_info.script_media_url)
        yield make_script_dto("text",prompt,script_info.script_id)
    else:
        prompt = get_fmt_prompt(app,user_id,script_info.script_prompt,profile_array_str=script_info.script_profile)
        if not prompt:
            prompt = ""
        for i in prompt:
            msg =  make_script_dto("text",i,script_info.script_id)
            yield msg
            time.sleep(0.01)
    log_script = generation_attend(app,attend,script_info)
    log_script.script_content = prompt
    log_script.script_role = ROLE_TEACHER
    db.session.add(log_script)
    span = trace.span(name="fix_script")
    span.end(output=prompt)
    trace_args ["output"] = trace_args["output"]+"\r\n"+prompt
    trace.update(**trace_args)

def generate_prompt_output(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,trace:Trace,trace_args):
    span = trace.span(name="prompt_sript")
    system = get_lesson_system(script_info.lesson_id)
    system_prompt = None if system == None or system == "" else get_fmt_prompt(app,user_id,system)
    prompt = get_fmt_prompt(app,user_id,script_info.script_prompt,profile_array_str=script_info.script_profile)
    resp = invoke_llm(app,span,
        model=script_info.script_model,
        stream=True,
        system=system_prompt,
        temperature=script_info.script_temprature,
        message=prompt)
    response_text = ""
    for chunk in resp:
        current_content = chunk.result
        if isinstance(current_content ,str):
            response_text += current_content
            yield make_script_dto("text", current_content,script_info.script_id)
    trace_args ["output"] = trace_args["output"]+"\r\n"+response_text
    trace.update(**trace_args)
    log_script = generation_attend(app,attend,script_info)
    log_script.script_content = response_text
    log_script.script_role = ROLE_TEACHER
    db.session.add(log_script)
   

OUTPUT_HANDLERS = {
    SCRIPT_TYPE_FIX: generate_fix_output,
    SCRIPT_TYPE_PORMPT: generate_prompt_output,
}


def handle_output(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace:Trace,trace_args
):
    if script_info.script_type in OUTPUT_HANDLERS:
        app.logger.info("generation output lesson_id:{}  script type:{},user_id:{},script_index:{}".format(script_info.lesson_id, script_info.script_type,user_id,script_info.script_index))
        yield from OUTPUT_HANDLERS[script_info.script_type](app,user_id,attend,script_info,trace,trace_args)
        yield make_script_dto("text_end","",script_info.script_id)
    else:
        raise AppException("script type not found")
    span = trace.span(name="output_script")
    span.end()
    db.session.flush()