











import json
from re import U
import time
from flask import Flask
from flaskr.service.common.models import AppException
from flaskr.service.order.consts import ATTEND_STATUS_BRANCH, ATTEND_STATUS_IN_PROGRESS
from flaskr.service.order.funs import init_buy_record
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.study.const import INPUT_TYPE_BRANCH, INPUT_TYPE_CHECKCODE, INPUT_TYPE_CONTINUE, INPUT_TYPE_PHONE, INPUT_TYPE_SELECT
from flaskr.service.study.models import AICourseAttendAsssotion
from flaskr.service.user.funs import send_sms_code_without_check
from flaskr.service.lesson.models import AILesson, AILessonScript
from flaskr.service.lesson.const import UI_TYPE_BRANCH, UI_TYPE_BUTTON, UI_TYPE_CHECKCODE, UI_TYPE_INPUT, UI_TYPE_PHONE, UI_TYPE_SELECTION, UI_TYPE_TO_PAY
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.study.utils import make_script_dto
from flaskr.dao import db


UI_HANDLE_MAP = {
}
def register_ui_handler(ui_type):
    def decorator(func):
        print(f"register_input_handler {ui_type} ==> {func.__name__}")
        UI_HANDLE_MAP[ui_type] = func
        return func
    return decorator





@register_ui_handler(UI_TYPE_INPUT)
def handle_input_text(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace,trace_args):
    yield  make_script_dto("input",script_info.script_ui_content,script_info.script_id) 
@register_ui_handler(UI_TYPE_BUTTON)
def handle_input_button(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace,trace_args):
    btn = [{
                            "label":script_info.script_ui_content,
                            "value":script_info.script_ui_content,
                            "type":INPUT_TYPE_CONTINUE
                        }]
    yield make_script_dto("buttons",{"title":"接下来","buttons":btn},script_info.script_id)
@register_ui_handler(UI_TYPE_BRANCH)
def handle_input_branch(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace,trace_args):
    app.logger.info("branch")
    branch_info = json.loads(script_info.script_other_conf)
    branch_key = branch_info.get("var_name","")
    profile = get_user_profiles(app,user_id,[branch_key])
    branch_value = profile.get(branch_key,"")
    jump_rule = branch_info.get("jump_rule",[])
    for rule in jump_rule:
        if branch_value == rule.get("value",""):
            attend_info = AICourseLessonAttend.query.filter(AICourseLessonAttend.attend_id == attend.attend_id).first()
            next_lesson = AILesson.query.filter(AILesson.lesson_feishu_id == rule.get("lark_table_id",""), AILesson.status == 1, func.length(AILesson.lesson_no)>2).first()
            if next_lesson:
                next_attend = AICourseLessonAttend.query.filter(AICourseLessonAttend.user_id==user_id, AICourseLessonAttend.course_id==course_id,AICourseLessonAttend.lesson_id==next_lesson.lesson_id).first()
                if next_attend:
                    assoation =AICourseAttendAsssotion()
                    assoation.from_attend_id = attend_info.attend_id
                    assoation.to_attend_id = next_attend.attend_id 
                    assoation.user_id = user_id
                    db.session.add(assoation)
                    next_attend.status = ATTEND_STATUS_IN_PROGRESS
                    next_attend.script_index =0
                    attend_info.status = ATTEND_STATUS_BRANCH
                    db.session.flush()
                    attend_info = next_attend

    btn = [{
        "label":script_info.script_ui_content,
        "value":script_info.script_ui_content,
        "type":INPUT_TYPE_BRANCH
    }]
    yield make_script_dto("buttons",{"title":"接下来","buttons":btn},script_info.script_id)


@register_ui_handler(UI_TYPE_SELECTION)
def handle_input_selection(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace,trace_args):
    btns = json.loads(script_info.script_other_conf)["btns"]
    for btn in btns:
        btn["type"] = INPUT_TYPE_SELECT
    yield make_script_dto("buttons",{"title":script_info.script_ui_content,"buttons":btns},script_info.script_id)




@register_ui_handler(UI_TYPE_PHONE)
def handle_input_phone(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace,trace_args):
    yield make_script_dto(INPUT_TYPE_PHONE,script_info.script_ui_content,script_info.script_id)



@register_ui_handler(UI_TYPE_CHECKCODE)
def handle_input_checkcode(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace,trace_args):
    try:
        expires = send_sms_code_without_check(app,user_id,input)
        yield make_script_dto(INPUT_TYPE_CHECKCODE,expires,script_info.script_id)
    except AppException as e:
        for i in e.message:
            yield make_script_dto("text",i,script_info.script_id)
            time.sleep(0.01)
        yield make_script_dto("text_end","",script_info.script_id)
@register_ui_handler(UI_TYPE_TO_PAY)
def handle_input_to_pay(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace,trace_args):
    order =  init_buy_record(app,user_id,attend.course_id)
    btn = [{
        "label":script_info.script_ui_content,
        "value":order.order_id
    }]
    yield make_script_dto("order",{"title":"买课！","buttons":btn},script_info.script_id)


def handle_ui(app:Flask,user_id:str,attend:AICourseLessonAttend,script_info:AILessonScript,input:str,trace,trace_args):
    if script_info.script_ui_type in UI_HANDLE_MAP:
        app.logger.info("generation ui lesson_id:{}  script type:{},user_id:{},script_index:{}".format(script_info.lesson_id, script_info.script_type,user_id,script_info.script_index))
        yield from UI_HANDLE_MAP[script_info.script_ui_type](app,user_id,attend,script_info,input,trace,trace_args)
    else:
        raise AppException("script type not found")
    span = trace.span(name="ui_script")
    span.end()
    db.session.flush()