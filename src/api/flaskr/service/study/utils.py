


import datetime
import json
import re
import time
from typing import Generator
from flask import Flask
from langchain.prompts import PromptTemplate
from ...api.langfuse import langfuse_client as langfuse
from ...api.llm import invoke_llm
from ...service.common.models import AppException
from ...service.lesson.const import CONTENT_TYPE_IMAGE, LESSON_TYPE_BRANCH_HIDDEN, SCRIPT_TYPE_FIX, SCRIPT_TYPE_PORMPT, SCRIPT_TYPE_SYSTEM, UI_TYPE_BRANCH, UI_TYPE_BUTTON, UI_TYPE_CHECKCODE, UI_TYPE_CONTINUED, UI_TYPE_INPUT, UI_TYPE_LOGIN, UI_TYPE_PHONE, UI_TYPE_SELECTION, UI_TYPE_TO_PAY
from ...service.lesson.models import AICourse, AILesson, AILessonScript
from ...service.order.consts import ATTEND_STATUS_BRANCH, ATTEND_STATUS_COMPLETED, ATTEND_STATUS_IN_PROGRESS, ATTEND_STATUS_NOT_STARTED, ATTEND_STATUS_VALUES
from ...service.order.funs import AICourseLessonAttendDTO, init_buy_record, init_trial_lesson
from ...service.order.models import AICourseBuyRecord, AICourseLessonAttend
from ...service.profile.funcs import get_user_profiles, save_user_profiles
from ...service.study.const import INPUT_TYPE_CHECKCODE, INPUT_TYPE_CONTINUE, INPUT_TYPE_LOGIN, INPUT_TYPE_PHONE, INPUT_TYPE_SELECT, INPUT_TYPE_START, INPUT_TYPE_TEXT, ROLE_STUDENT, ROLE_TEACHER
from ...service.study.dtos import AILessonAttendDTO, ScriptDTO
from ...service.study.models import AICourseAttendAsssotion, AICourseLessonAttendScript
from ...service.user.funs import send_sms_code_without_check, verify_sms_code_without_phone
from ...service.user.models import User
from ...dao import db


def get_current_lesson(app: Flask, lesssons:list[AICourseLessonAttendDTO] )->AICourseLessonAttendDTO:
    return lesssons[0]
def generation_attend(app:Flask,attend:AICourseLessonAttendDTO,script_info:AILessonScript)->AICourseLessonAttendScript:
    attendScript = AICourseLessonAttendScript()
    attendScript.attend_id = attend.attend_id
    attendScript.user_id = attend.user_id
    attendScript.lesson_id =  script_info.lesson_id
    attendScript.course_id = attend.course_id   
    attendScript.script_id = script_info.script_id
    return attendScript

def check_phone_number(app,user_id,input):
    if not re.match(r'^1[3-9]\d{9}$', input):
        return False
    return True

# 得到一个课程的System Prompt

def get_lesson_system(lesson_id:str)->str:
        # 缓存逻辑 
        lesson_ids = [lesson_id]
        lesson = AILesson.query.filter(AILesson.lesson_id == lesson_id).first()
        lesson_no = lesson.lesson_no 
        parent_no = lesson_no
        if len(parent_no)>2:
            parent_no = parent_no[:2]
        if parent_no != lesson_no:
            parent_lesson = AILesson.query.filter(AILesson.lesson_no == parent_no).first()
            if parent_lesson:
                lesson_ids.append(parent_lesson.lesson_id)
        scripts = AILessonScript.query.filter(AILessonScript.lesson_id.in_(lesson_ids) == True,AILessonScript.script_type==SCRIPT_TYPE_SYSTEM).all()
        if len(scripts)>0:
            for script in scripts:
                if script.lesson_id == lesson_id:
                    return script.script_prompt
            return scripts[0].script_prompt
        return None
def fmt(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    else:
        return o.__json__()

def get_profile_array(profile:str)->list:
    return re.findall(r'\[(.*?)\]', profile)




def get_lesson_and_attend_info(app:Flask,parent_no,course_id,user_id):
    lessons = AILesson.query.filter(AILesson.lesson_no.like(parent_no+'%'),AILesson.course_id ==course_id,AILesson.lesson_type !=LESSON_TYPE_BRANCH_HIDDEN, AILesson.status==1 ).all()
    if len(lessons)==0:
        return [] 
    attend_infos = AICourseLessonAttend.query.filter(AICourseLessonAttend.lesson_id.in_([lesson.lesson_id for lesson in lessons]),AICourseLessonAttend.user_id == user_id ).all()
    attend_lesson_infos = [{'attend':attend,'lesson': [lesson for lesson in lessons if lesson.lesson_id == attend.lesson_id][0]} for attend in attend_infos]
    attend_lesson_infos =  sorted(attend_lesson_infos, key=lambda x: (len(x['lesson'].lesson_no), x['lesson'].lesson_no)) 
    app.logger.info("attends:{}".format(",".join("'"+a['lesson'].lesson_no+"'" for a in attend_lesson_infos)))
    return attend_lesson_infos

# 从文本中提取json对象
def extract_json(app:Flask,text:str):
    stack = []
    start = None
    for i, char in enumerate(text):
        if char == '{':
            if not stack:
                start = i
            stack.append(char)
        elif char == '}':
            if stack:
                stack.pop()
                if not stack:
                    json_str = text[start:i+1]
                    try:
                        json_obj = json.loads(json_str)
                        return json_obj
                    except json.JSONDecodeError:
                        pass
    return {}
def get_fmt_prompt(app:Flask,user_id:str,profile_tmplate:str,input:str=None,profile_array_str:str=None)->str:
    app.logger.info("raw prompt:"+profile_tmplate)
    propmpt_keys = []
    profiles = {}
    if profile_array_str:
        propmpt_keys = get_profile_array(profile_array_str) 
        profiles = get_user_profiles(app,user_id,propmpt_keys)
    else:
        profiles = get_user_profiles(app,user_id)
        propmpt_keys = list(profiles.keys())
    if input:
        profiles['input'] = input
        propmpt_keys.append('input')
    app.logger.info(propmpt_keys)
    app.logger.info(profiles)
    prompt_template_lc = PromptTemplate.from_template(profile_tmplate)
    keys = prompt_template_lc.input_variables
    fmt_keys = {}
    for key in keys:
        if key in profiles:
            fmt_keys[key] = profiles[key]
        else:
            fmt_keys[key] = '目前未知'
            app.logger.info('key not found:'+key+ ' ,user_id:'+user_id)
    app.logger.info(fmt_keys)
    if len(fmt_keys) == 0:
        if len(profile_tmplate) == 0:
            prompt = input
        else: 
            prompt = profile_tmplate
    else:
        prompt = prompt_template_lc.format(**fmt_keys)
    app.logger.info('fomat input:{}'.format(prompt))
    return prompt
 


def get_script(app:Flask,attend_id:str,next:bool) :
    attend_info = AICourseLessonAttend.query.filter(AICourseLessonAttend.attend_id ==attend_id).first()
    attend_infos = []
    app.logger.info("get next script,current:{},next:{}".format(attend_info.script_index,next))
    if attend_info.status == ATTEND_STATUS_NOT_STARTED or attend_info.script_index == 0:
        attend_info.status = ATTEND_STATUS_IN_PROGRESS
        attend_info.script_index = 1
           # 检查是否是第一节课
        lesson = AILesson.query.filter(AILesson.lesson_id == attend_info.lesson_id).first()
        attend_infos.append(AILessonAttendDTO(lesson.lesson_no,lesson.lesson_name,lesson.lesson_id,ATTEND_STATUS_VALUES[ATTEND_STATUS_IN_PROGRESS]))
        app.logger.info(lesson.lesson_no)
        app.logger.info(lesson.lesson_no[-2:])   
        if len(lesson.lesson_no)>=2 and lesson.lesson_no[-2:] == '01':
            # 第一节课
            app.logger.info('first lesson')
            parent_lesson = AILesson.query.filter(AILesson.lesson_no == lesson.lesson_no[:-2]).first()
            parent_attend = AICourseLessonAttend.query.filter(AICourseLessonAttend.lesson_id == parent_lesson.lesson_id,AICourseLessonAttend.user_id == attend_info.user_id).first()
            if parent_attend.status == ATTEND_STATUS_NOT_STARTED:
                parent_attend.status = ATTEND_STATUS_IN_PROGRESS
                attend_infos.append(AILessonAttendDTO(parent_lesson.lesson_no,parent_lesson.lesson_name,parent_lesson.lesson_id,ATTEND_STATUS_VALUES[ATTEND_STATUS_IN_PROGRESS]))
    elif attend_info.status == ATTEND_STATUS_BRANCH:
        # 分支课程
        app.logger.info('branch')
        current = attend_info
        assoation = AICourseAttendAsssotion.query.filter(AICourseAttendAsssotion.from_attend_id==current.attend_id).first()
        if assoation:
            app.logger.info('found assoation')
            current = AICourseLessonAttend.query.filter(AICourseLessonAttend.attend_id==assoation.to_attend_id).first()
        while current.status == ATTEND_STATUS_BRANCH:
            # 分支课程
            assoation = AICourseAttendAsssotion.query.filter(AICourseAttendAsssotion.from_attend_id==current.attend_id).first()
            if assoation:
                current = AICourseLessonAttend.query.filter(AICourseLessonAttend.attend_id==assoation.to_attend_id).first()
        app.logger.info('to get branch script')
        script_info,attend_infos = get_script(app,current.attend_id,next)
        if script_info:
            return script_info,[]
        else:
            current.status = ATTEND_STATUS_COMPLETED
            attend_info.status = ATTEND_STATUS_IN_PROGRESS
            db.session.commit()
            return get_script(app,attend_id,next)
    elif next:
        attend_info.script_index = attend_info.script_index + 1
    script_info = AILessonScript.query.filter(AILessonScript.lesson_id==attend_info.lesson_id,AILessonScript.status ==1,AILessonScript.script_index==attend_info.script_index).first()
    if not script_info:
        app.logger.info('no script found')
        app.logger.info(attend_info.lesson_id)

        attend_info.status = ATTEND_STATUS_COMPLETED
        lesson = AILesson.query.filter(AILesson.lesson_id == attend_info.lesson_id).first()

        attend_infos.append(AILessonAttendDTO(lesson.lesson_no,lesson.lesson_name,lesson.lesson_id,ATTEND_STATUS_VALUES[ATTEND_STATUS_COMPLETED]))
    db.session.commit()
    return script_info,attend_infos

def get_script_by_id(app: Flask,script_id:str)->AILessonScript:
    return AILessonScript.query.filter_by(script_id=script_id).first()

def make_script_dto(script_type,script_content,script_id)->str:
    return    'data: '+json.dumps(ScriptDTO(script_type,script_content,script_id),default=fmt)+'\n\n'.encode('utf-8').decode('utf-8')

def update_attend_lesson_info(app:Flask,attend_id:str)->list[AILessonAttendDTO]:
    res = []
    attend_info = AICourseLessonAttend.query.filter(AICourseLessonAttend.attend_id ==attend_id).first()
    lesson = AILesson.query.filter(AILesson.lesson_id == attend_info.lesson_id).first()
    lesson_no = lesson.lesson_no
    parent_no = lesson_no
    attend_info.status = ATTEND_STATUS_COMPLETED
    res.append(AILessonAttendDTO(lesson_no,lesson.lesson_name,lesson.lesson_id,ATTEND_STATUS_VALUES[ATTEND_STATUS_COMPLETED]))
    if len(parent_no)>2:
        parent_no = parent_no[:2]
    app.logger.info('parent_no:'+parent_no)
    attend_lesson_infos =  get_lesson_and_attend_info(app,parent_no,lesson.course_id,attend_info.user_id)

    if attend_lesson_infos[-1]['attend'].attend_id == attend_id:
        # 最后一个已经完课
        # 整体章节完课
        attend_lesson_infos[0]['attend'].status = ATTEND_STATUS_COMPLETED
        res.append(AILessonAttendDTO(attend_lesson_infos[0]['lesson'].lesson_no,attend_lesson_infos[0]['lesson'].lesson_name,attend_lesson_infos[0]['lesson'].lesson_id,ATTEND_STATUS_VALUES[ATTEND_STATUS_COMPLETED]))
        # 找到下一章节进行解锁
        next_no = str(int(parent_no)+1).zfill(2)
        next_lessons = get_lesson_and_attend_info(app,next_no,lesson.course_id,attend_info.user_id)
        if len(next_lessons) > 0 :
            # 解锁
            for next_lesson_attend in next_lessons:
                if next_lesson_attend['lesson'].lesson_no == next_no:
                    next_lesson_attend['attend'].status = ATTEND_STATUS_NOT_STARTED
                    res.append(AILessonAttendDTO(next_lesson_attend['lesson'].lesson_no,next_lesson_attend['lesson'].lesson_name,next_lesson_attend['lesson'].lesson_id,ATTEND_STATUS_VALUES[ATTEND_STATUS_NOT_STARTED]))
                if next_lesson_attend['lesson'].lesson_no == next_no+'01':
                    next_lesson_attend['attend'].status = ATTEND_STATUS_NOT_STARTED
                    res.append(AILessonAttendDTO(next_lesson_attend['lesson'].lesson_no,next_lesson_attend['lesson'].lesson_name,next_lesson_attend['lesson'].lesson_id,ATTEND_STATUS_VALUES[ATTEND_STATUS_NOT_STARTED]))

    for i in range(len(attend_lesson_infos)):
        app.logger.info(i)
        if i>0 and  attend_lesson_infos[i-1]['attend'].attend_id == attend_id:
            # 更新下一节
            app.logger.info('to update' + attend_lesson_infos[i]['lesson'].lesson_no)
            attend_lesson_infos[i]['attend'].status = ATTEND_STATUS_NOT_STARTED
            res.append(AILessonAttendDTO( attend_lesson_infos[i]['lesson'].lesson_no,  attend_lesson_infos[i]['lesson'].lesson_name,  attend_lesson_infos[i]['lesson'].lesson_id,ATTEND_STATUS_VALUES[ATTEND_STATUS_NOT_STARTED]))
    return res

