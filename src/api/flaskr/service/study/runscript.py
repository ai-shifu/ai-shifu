


import datetime
import json
import re
import time
from typing import Generator
from flask import Flask
from langchain.prompts import PromptTemplate
from sqlalchemy import func
from ...api.langfuse import langfuse_client as langfuse
from ...api.llm import invoke_llm
from ...service.common.models import AppException
from ...service.lesson.const import CONTENT_TYPE_IMAGE, LESSON_TYPE_BRANCH_HIDDEN, SCRIPT_TYPE_FIX, SCRIPT_TYPE_PORMPT, SCRIPT_TYPE_SYSTEM, UI_TYPE_BRANCH, UI_TYPE_BUTTON, UI_TYPE_CHECKCODE, UI_TYPE_CONTINUED, UI_TYPE_INPUT, UI_TYPE_LOGIN, UI_TYPE_PHONE, UI_TYPE_SELECTION, UI_TYPE_TO_PAY
from ...service.lesson.models import AICourse, AILesson, AILessonScript
from ...service.order.consts import ATTEND_STATUS_BRANCH, ATTEND_STATUS_COMPLETED, ATTEND_STATUS_IN_PROGRESS, ATTEND_STATUS_NOT_STARTED, ATTEND_STATUS_VALUES
from ...service.order.funs import AICourseLessonAttendDTO, init_buy_record, init_trial_lesson
from ...service.order.models import AICourseBuyRecord, AICourseLessonAttend
from ...service.profile.funcs import get_user_profiles, save_user_profiles
from ...service.study.const import INPUT_TYPE_BRANCH, INPUT_TYPE_CHECKCODE, INPUT_TYPE_CONTINUE, INPUT_TYPE_LOGIN, INPUT_TYPE_PHONE, INPUT_TYPE_SELECT, INPUT_TYPE_START, INPUT_TYPE_TEXT, ROLE_STUDENT, ROLE_TEACHER
from ...service.study.dtos import AILessonAttendDTO, ScriptDTO
from ...service.study.models import AICourseAttendAsssotion, AICourseLessonAttendScript
from ...service.user.funs import send_sms_code_without_check, verify_sms_code_without_phone
from ...service.user.models import User
from ...dao import db
from .utils import *
from .input_funcs import BreakException, handle_input 
from .output_funcs import handle_output

def run_script(app: Flask, user_id: str, course_id: str, lesson_id: str=None,input:str=None,input_type:str=None,script_id:str = None)->Generator[ScriptDTO,None,None]:
    with app.app_context():
        course_info = AICourse.query.filter(AICourse.course_id == course_id).first()
        if not course_info:
            course_info = AICourse.query.first()
            course_id = course_info.course_id
        if not lesson_id:
            buy_record = AICourseBuyRecord.query.filter_by(user_id=user_id, course_id=course_id).first() 
            if not buy_record:
                lessons = init_trial_lesson(app, user_id, course_id)
                app.logger.info("user_id:{},course_id:{},lesson_id:{}".format(user_id,course_id,lesson_id))
                attend = get_current_lesson(app,lessons)
                app.logger.info("{}".format(attend))
                lesson_id = attend.lesson_id
        else:
            # 获取课程记录
            app.logger.info("user_id:{},course_id:{},lesson_id:{}".format(user_id,course_id,lesson_id))
            attend_info = AICourseLessonAttend.query.filter_by(user_id=user_id, course_id=course_id,lesson_id=lesson_id).first()
            if not attend_info:
                # 没有课程记录
                for i in "请购买课程":
                    yield make_script_dto("text",i,None)
                    time.sleep(0.01)
                yield make_script_dto("text_end","",None)
                return
            attend = AICourseLessonAttendDTO(attend_info.attend_id,attend_info.lesson_id,attend_info.course_id,attend_info.user_id,attend_info.status,attend_info.script_index)
            db.session.commit()
        # Langfuse 集成 
        trace_args ={}
        trace_args['user_id'] = user_id
        trace_args['session_id'] = attend.attend_id
        trace_args['input'] = input 
        trace_args['name'] = "ai-python"
        trace = langfuse.trace(**trace_args)
        trace_args["output"]=""
        next = False
        
       # 如果有用户输入,就得到当前这一条,否则得到下一条
        if script_id:
            # 如果有指定脚本
            # 为了测试使用
            script_info = get_script_by_id(app,script_id)
        else:
            # 获取当前脚本
            script_info,attend_updates = get_script(app,attend_id=attend.attend_id,next=next)
            if len(attend_updates)>0:
                for attend_update in attend_updates:
                    if len(attend_update.lesson_no) > 2:
                        yield make_script_dto("lesson_update",attend_update.__json__(),"")
                    else:
                        yield make_script_dto("chapter_update",attend_update.__json__(),"") 
        if script_info:
            try:
                # 处理用户输入
                response = handle_input(app,user_id,input_type,attend,script_info,input,trace,trace_args)
                if response:
                    yield from response
                # 如果是Start或是Continue，就不需要再次获取脚本
                if  input_type == INPUT_TYPE_START:
                    next = False
                else:
                    next = True
                while True:
                    if next:
                        script_info,attend_updates = get_script(app,attend_id=attend.attend_id,next=next)
                    next = True
                    if len(attend_updates)>0:
                        for attend_update in attend_updates:
                            if len(attend_update.lesson_no) > 2:
                                yield make_script_dto("lesson_update",attend_update.__json__(),"")
                            else:
                                yield make_script_dto("chapter_update",attend_update.__json__(),"")
                    if script_info:
                        response = handle_output(app,user_id,attend,script_info,input,trace,trace_args) 
                        if response:
                            yield from response
                        if script_info.script_ui_type == UI_TYPE_CONTINUED:
                            continue
                        else:
                            break
                    else:
                        break
                   
                if script_info:
                # 返回下一轮交互
                # 返回  下一轮的交互方式
                    app.logger.info("ui_type:{}".format(script_info.script_ui_type))
                    if script_info.script_ui_type == UI_TYPE_INPUT:
                        yield  make_script_dto("input",script_info.script_ui_content,script_info.script_id) 
                    elif  script_info.script_ui_type == UI_TYPE_BUTTON:
                        btn = [{
                            "label":script_info.script_ui_content,
                            "value":script_info.script_ui_content,
                            "type":INPUT_TYPE_CONTINUE
                        }]
                        yield make_script_dto("buttons",{"title":"接下来","buttons":btn},script_info.script_id)
                    elif script_info.script_ui_type == UI_TYPE_BRANCH:
                          # 分支课程
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
                                        db.session.commit()
                                        next = False
                                        attend_info = next_attend

                        btn = [{
                            "label":script_info.script_ui_content,
                            "value":script_info.script_ui_content,
                            "type":INPUT_TYPE_BRANCH
                        }]
                        yield make_script_dto("buttons",{"title":"接下来","buttons":btn},script_info.script_id)
                    elif script_info.script_ui_type == UI_TYPE_SELECTION:
                        btns = json.loads(script_info.script_other_conf)["btns"]
                        for btn in btns:
                            btn["type"] = INPUT_TYPE_SELECT
                        
                        yield make_script_dto("buttons",{"title":script_info.script_ui_content,"buttons":btns},script_info.script_id)
                    elif  script_info.script_ui_type == UI_TYPE_PHONE:
                        yield make_script_dto(INPUT_TYPE_PHONE,script_info.script_ui_content,script_info.script_id)
                    elif script_info.script_ui_type == UI_TYPE_CHECKCODE:
                        try:
                            expires = send_sms_code_without_check(app,user_id,input)
                            yield make_script_dto(INPUT_TYPE_CHECKCODE,expires,script_info.script_id)
                        except AppException as e:
                            for i in e.message:
                                yield make_script_dto("text",i,script_info.script_id)
                                time.sleep(0.01)
                            yield make_script_dto("text_end","",script_info.script_id)
                    elif script_info.script_ui_type == UI_TYPE_LOGIN:
                        yield make_script_dto(INPUT_TYPE_LOGIN,script_info.script_ui_content,script_info.script_id)
                        # 这里控制暂时是否启用登录
                    elif script_info.script_ui_type == UI_TYPE_TO_PAY:
                        order =  init_buy_record(app,user_id,course_id,999)
                        btn = [{
                            "label":script_info.script_ui_content,
                            "value":order.record_id
                        }]
                        yield make_script_dto("order",{"title":"买课！","buttons":btn},script_info.script_id)
                    elif  script_info.script_ui_type == UI_TYPE_CONTINUED:
                        next = True
                        input_type= None 
                
                else:
                    attends =  update_attend_lesson_info(app,attend.attend_id)
                    for attend_update in attends:
                            if len(attend_update.lesson_no) > 2:
                                yield make_script_dto("lesson_update",attend_update.__json__(),"")
                            else:
                                yield make_script_dto("chapter_update",attend_update.__json__(),"") 
                    app.logger.info("script_info is None")
            except BreakException as e:
                return
        else:
                    app.logger.info("script_info is None,to update attend")
                    attends =  update_attend_lesson_info(app,attend.attend_id)
                    for attend_update in attends:
                            if len(attend_update.lesson_no) > 2:
                                yield make_script_dto("lesson_update",attend_update.__json__(),"")
                            else:
                                yield make_script_dto("chapter_update",attend_update.__json__(),"") 
        db.session.commit()
