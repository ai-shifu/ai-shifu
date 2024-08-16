# 输入处理的函数
# 全部的输入处理函数都在这里
# 正常返回为yield，异常返回为raise



import json
import time
from trace import Trace
from flask import Flask
from sqlalchemy import func

from flaskr.api.llm import invoke_llm
from flaskr.service.common.models import AppException
from flaskr.service.profile.funcs import save_user_profiles
from flaskr.service.study.utils import extract_json, generation_attend, get_fmt_prompt
from flaskr.service.user.funs import verify_sms_code_without_phone

from ...service.study.runscript import check_phone_number, get_profile_array
from ...service.lesson.models import AILessonScript
from ...service.order.models import AICourseLessonAttend
from ...service.study.const import INPUT_TYPE_LOGIN, ROLE_STUDENT, ROLE_TEACHER
from ...dao import db
from .utils import *


class BreakException(Exception):
    pass

def handle_input_text(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace:Trace,trace_args):
    prompt = get_fmt_prompt(app,user_id,script_info.script_check_prompt,input,script_info.script_profile)
    ## todo 换成通用的
    log_script = generation_attend(app,attend,script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT 
    db.session.add(log_script)
    span = trace.span(name="user_input",input=input)
    resp = invoke_llm(app,
                      span,
        model=script_info.script_model,
        json=True,
        stream=True,
        temperature=script_info.script_temprature,
        message=prompt)
    response_text = ""
    check_success = False
    for i in resp:
        current_content = i.result
        if isinstance(current_content ,str):
            response_text += current_content
    jsonObj = extract_json(app,response_text)
    check_success = jsonObj.get("result","")=="ok"
    if check_success:
        app.logger.info('check success')
        profile_tosave = jsonObj.get("parse_vars")
        save_user_profiles(app,user_id,profile_tosave)
        for key in profile_tosave:
            yield make_script_dto("profile_update",{"key":key,"value":profile_tosave[key]},script_info.script_id)
            time.sleep(0.01)
        # input = None
        # next = True
        # input_type = None 
        span.end()
        db.session.commit() 
        
    else:
        reason = jsonObj.get("reason",response_text)
        for text in reason:
            yield make_script_dto("text",text,script_info.script_id)
            time.sleep(0.01)
        yield make_script_dto("text_end","",script_info.script_id)
        log_script = generation_attend(app,attend,script_info)
        log_script.script_content = response_text
        log_script.script_role = ROLE_TEACHER
        db.session.add(log_script)
        span.end(output=response_text)
        trace_args ["output"] = trace_args["output"]+"\r\n"+response_text
        trace.update(**trace_args)
        db.session.commit()
        yield make_script_dto("input",script_info.script_ui_content,script_info.script_id) 
        raise BreakException


def handle_input_continue(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace:Trace,trace_args):
    log_script = generation_attend(app,attend,script_info)
    log_script.script_content = "继续"
    log_script.script_role = ROLE_STUDENT
    db.session.add(log_script)
    span = trace.span(name="user_continue",input=input)
    span.end()
       # 分支课程
    if script_info.script_ui_type == UI_TYPE_BRANCH:
        app.logger.info("branch")
        branch_info = json.loads(script_info.script_other_conf)
        branch_key = branch_info.get("var_name","")
        profile = get_user_profiles(app,user_id,[branch_key])
        branch_value = profile.get(branch_key,"")
        jump_rule = branch_info.get("jump_rule",[])
        if attend.status != ATTEND_STATUS_BRANCH:
            for rule in jump_rule:
                if branch_value == rule.get("value",""):
                    attend_info = AICourseLessonAttend.query.filter(AICourseLessonAttend.attend_id == attend.attend_id).first()
                    next_lesson = AILesson.query.filter(AILesson.lesson_feishu_id == rule.get("lark_table_id",""), AILesson.status == 1, func.length(AILesson.lesson_no)>2).first()
                    if next_lesson:
                        next_attend = AICourseLessonAttend.query.filter(AICourseLessonAttend.user_id==user_id, AICourseLessonAttend.course_id==next_lesson.course_id,AICourseLessonAttend.lesson_id==next_lesson.lesson_id).first()
                        if next_attend:
                            assoation = AICourseAttendAsssotion.query.filter(
                                AICourseAttendAsssotion.from_attend_id == attend_info.attend_id, 
                                AICourseAttendAsssotion.to_attend_id == next_attend.attend_id).first()
                            if not assoation:
                                assoation =AICourseAttendAsssotion()
                                assoation.from_attend_id = attend_info.attend_id
                                assoation.to_attend_id = next_attend.attend_id 
                                assoation.user_id = user_id
                                db.session.add(assoation)
                            next_attend.status = ATTEND_STATUS_IN_PROGRESS
                            next_attend.script_index =0
                            attend_info.status = ATTEND_STATUS_BRANCH
                            attend_info = next_attend
                            app.logger.info("branch jump")

    db.session.commit()

def handle_input_select(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace:Trace,trace_args):
    profile_keys = get_profile_array(script_info.script_ui_profile)
    profile_tosave = {}
    if len(profile_keys) == 0 :
        btns = json.loads(script_info.script_other_conf)
        conf_key = btns.get('var_name','input')
        profile_tosave[conf_key] = input
    for k in profile_keys:
        profile_tosave[k]=input
    save_user_profiles(app,user_id,profile_tosave)
    log_script = generation_attend(app,attend,script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT
    db.session.add(log_script)
    # input = None
    # next = True
    # input_type = None
    span = trace.span(name="user_select",input=input)
    span.end()
    db.session.commit()
    
def handle_input_phone(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace:Trace,trace_args):
    log_script = generation_attend(app,attend,script_info)
    log_script.script_content = input
    log_script.script_role = ROLE_STUDENT
    db.session.add(log_script)
    # input = None
    input_type =  None 
    span = trace.span(name="user_input_phone",input=input)
    response_text ="请输入正确的手机号" 
    if not check_phone_number(app,user_id,input):
        for i in response_text:
            yield make_script_dto("text",i,script_info.script_id)
            time.sleep(0.01)
        yield make_script_dto("text_end","",script_info.script_id)
        yield make_script_dto(UI_TYPE_PHONE,script_info.script_ui_content,script_info.script_id) 
        log_script = generation_attend(app,attend,script_info)
        log_script.script_content = response_text
        log_script.script_role = ROLE_TEACHER
        db.session.add(log_script)
        span.end(output=response_text)
        # span.end()
        db.session.commit()
        raise BreakException
    span.end()

def handle_input_checkcode(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace:Trace,trace_args):
    try:
        ret = verify_sms_code_without_phone(app,user_id,input)
        yield make_script_dto("profile_update",{"key":"phone","value":ret.userInfo.mobile},script_info.script_id)
        yield make_script_dto("user_login",{"phone":ret.userInfo.mobile,"user_id":ret.userInfo.user_id},script_info.script_id)
        input = None
        span = trace.span(name="user_input_phone",input=input)
        span.end()
        
    except AppException as e:
        for i in e.message:
            yield make_script_dto("text",i,script_info.script_id)
            time.sleep(0.01)
        yield make_script_dto("text_end","",script_info.script_id)
        yield make_script_dto(INPUT_TYPE_CHECKCODE,script_info.script_ui_content,script_info.script_id)
        log_script = generation_attend(app,attend,script_info)
        log_script.script_content = e.message
        log_script.script_role = ROLE_TEACHER
        db.session.add(log_script)
        raise BreakException

def handle_input_login(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace:Trace,trace_args):
    yield make_script_dto(INPUT_TYPE_LOGIN,{"phone":ret.userInfo.mobile,"user_id":ret.userInfo.user_id},script_info.script_id)

def handle_input_start(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace:Trace,trace_args):
    # yield make_script_dto("text","",script_info.script_id)
    return None

UI_HANDLE_MAP = {
   INPUT_TYPE_START:handle_input_start,
    INPUT_TYPE_TEXT:handle_input_text,
    INPUT_TYPE_CONTINUE:handle_input_continue,
    INPUT_TYPE_SELECT:handle_input_select,
    INPUT_TYPE_PHONE:handle_input_phone,
    INPUT_TYPE_CHECKCODE:handle_input_checkcode,
    INPUT_TYPE_LOGIN:handle_input_login,
    # INPUT_TYPE_TO_PAY:handle_input_to_pay, 
}

def handle_input(app:Flask,user_id:str,input_type:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace:Trace,trace_args
):
    app.logger.info(f"handle_input {input_type},user_id:{user_id},input:{input} ")
    if input_type in UI_HANDLE_MAP:
        respone =  UI_HANDLE_MAP[input_type](app,user_id,attend,script_info,input,trace,trace_args)
        if respone:
            yield from respone
    else:
        return None