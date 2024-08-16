from concurrent.futures import thread
import datetime
import json
import re
import openai
from typing import Generator
from flask import Flask, typing

from flaskr.service.study.const import INPUT_TYPE_BRANCH, INPUT_TYPE_CHECKCODE, INPUT_TYPE_CONTINUE, INPUT_TYPE_LOGIN, INPUT_TYPE_PHONE, INPUT_TYPE_SELECT, ROLE_VALUES
from ...service.study.dtos import AILessonAttendDTO, StudyRecordDTO
from ...service.user.models import User
from ...service.common  import AppException
from ...service.user.funs import get_sms_code_info, send_sms_code_without_check, verify_sms_code, verify_sms_code_without_phone
from ...common import register_schema_to_swagger
from ...service.profile.funcs import get_user_profiles, save_user_profiles
from ...service.order.consts import ATTEND_STATUS_BRANCH, ATTEND_STATUS_TYPES, ATTEND_STATUS_UNAVAILABE, ATTEND_STATUS_VALUES

from .dtos import AICourseDTO, StudyRecordItemDTO, StudyUIDTO
from ...service.lesson.const import CONTENT_TYPE_IMAGE, LESSON_TYPE_BRANCH_HIDDEN, SCRIPT_TYPE_FIX, SCRIPT_TYPE_PORMPT, SCRIPT_TYPE_SYSTEM, UI_TYPE_BRANCH, UI_TYPE_BUTTON, UI_TYPE_CHECKCODE, UI_TYPE_CONTINUED, UI_TYPE_INPUT, UI_TYPE_LOGIN, UI_TYPE_PHONE, UI_TYPE_SELECTION, UI_TYPE_TO_PAY
from ...dao import db

from ...service.lesson.models import AICourse, AILesson, AILessonScript
from ...service.order.funs import AICourseLessonAttendDTO, init_buy_record, init_trial_lesson
from ...service.order.models import ATTEND_STATUS_COMPLETED, ATTEND_STATUS_IN_PROGRESS, ATTEND_STATUS_NOT_STARTED, AICourseBuyRecord, AICourseLessonAttend
from .models import *
import time 

from ...api.langfuse import langfuse_client as langfuse
from ...api.llm import invoke_llm
from typing import List




def get_lesson_tree_to_study(app:Flask,user_id:str,course_id:str)->AICourseDTO:
    with app.app_context():
        course_info = AICourse.query.filter(AICourse.course_id == course_id).first()
        if not course_info:
            course_info = AICourse.query.first()
            course_id = course_info.course_id
          # 检查有没有购课记录
        buy_record = AICourseBuyRecord.query.filter_by(user_id=user_id, course_id=course_id).first() 
        if not buy_record:
            app.logger.info('no buy record found')
            # 没有购课记录
            # 生成体验课记录
            init_trial_lesson(app, user_id, course_id)
        lessons = AILesson.query.filter(course_id==course_id,AILesson.lesson_type !=LESSON_TYPE_BRANCH_HIDDEN, AILesson.status==1).all()
        lessons = sorted(lessons, key=lambda x: (len(x.lesson_no), x.lesson_no))
        attend_infos = AICourseLessonAttend.query.filter(AICourseLessonAttend.user_id == user_id,AICourseLessonAttend.course_id == course_id).all()
        attend_infos_map = {i.lesson_id:i for i in attend_infos}
        lessonInfos = []
        lesson_dict = {}
        for lesson in lessons:
            attend_info = attend_infos_map.get(lesson.lesson_id,None)
            if not attend_info:
                continue
            status = ATTEND_STATUS_VALUES[attend_info.status if  attend_info else  ATTEND_STATUS_UNAVAILABE]
            lessonInfo = AILessonAttendDTO(lesson.lesson_no,lesson.lesson_name,lesson.lesson_id,status, [])
            lesson_dict[lessonInfo.lesson_no] = lessonInfo
            if len(lessonInfo.lesson_no) == 2:  # 假设2位数是根节点
                lessonInfos.append(lessonInfo)
            else:
                # 获取父节点编号
                parent_no = lessonInfo.lesson_no[:-2]
                if parent_no in lesson_dict:
                    lesson_dict[parent_no].children.append(lessonInfo)
        course_info = AICourse.query.filter(AICourse.course_id == course_id).first()
        return AICourseDTO(course_id=course_id,course_name=course_info.course_name,lessons=lessonInfos)


# 获取学习记录

def get_study_record(app:Flask,user_id:str,lesson_id:str)->StudyRecordDTO:
    with app.app_context():

        lesson_info = AILesson.query.filter_by(lesson_id=lesson_id).first()
        lesson_ids = [lesson_id]
        if not lesson_info:
            return None
        if len(lesson_info.lesson_no) <= 2:
            lesson_infos = AILesson.query.filter(AILesson.lesson_no.like(lesson_info.lesson_no+'%')).all()
            lesson_ids = [lesson.lesson_id for lesson in lesson_infos]
        app.logger.info("lesson_ids:{}".format(lesson_ids))
        print("lesson_ids:{}".format(lesson_ids))
        attend_infos = AICourseLessonAttend.query.filter(AICourseLessonAttend.user_id==user_id,  AICourseLessonAttend.lesson_id.in_(lesson_ids)).order_by(AICourseLessonAttend.id).all()
        if not attend_infos:
            return None
        attend_ids = [attend_info.attend_id for attend_info in attend_infos]
        app.logger.info("attend_ids:{}".format(attend_ids))
        attend_scripts = AICourseLessonAttendScript.query.filter(AICourseLessonAttendScript.attend_id.in_(attend_ids)).order_by(AICourseLessonAttendScript.id).all()
        app.logger.info("attend_scripts:{}".format(len(attend_scripts)))
        index = len(attend_scripts)-1
       
        if len(attend_scripts) == 0:
            return StudyRecordDTO(None)
        lesson_id = attend_scripts[-1].lesson_id
        while lesson_id not in lesson_ids:
            lesson_id = attend_scripts[index].lesson_id
            index -= 1
        items =  [StudyRecordItemDTO(i.script_index,ROLE_VALUES[i.script_role],0,i.script_content,i.lesson_id if i.lesson_id in lesson_ids else lesson_id,i.id) for i in attend_scripts]
        ret = StudyRecordDTO(items)
        last_script_id = attend_scripts[-1].script_id
       


        last_script = AILessonScript.query.filter_by(script_id=last_script_id).first()
        app.logger.info("last_script:{}".format(last_script)) 
        if last_script.script_ui_type == UI_TYPE_INPUT:
            ret.ui = StudyUIDTO("input",last_script.script_ui_content,lesson_id)
        elif last_script.script_ui_type == UI_TYPE_BUTTON:
            btn = [{
                        "label":last_script.script_ui_content,
                        "value":last_script.script_ui_content,
                        "type":INPUT_TYPE_CONTINUE
                    }]
            ret.ui = StudyUIDTO("buttons",{"title":"接下来","buttons":btn},lesson_id)
        elif last_script.script_ui_type == UI_TYPE_CONTINUED:
            ret.ui = StudyUIDTO("buttons",{"title":"继续","buttons":[{"label":"继续","value":"继续","type":INPUT_TYPE_CONTINUE}]},lesson_id)
        elif last_script.script_ui_type == UI_TYPE_BRANCH:
            ret.ui = StudyUIDTO("buttons",{"title":"继续","buttons":[{"label":"继续","value":"继续","type":INPUT_TYPE_BRANCH}]},lesson_id)
        elif last_script.script_ui_type == UI_TYPE_SELECTION:
            btns = json.loads(last_script.script_other_conf)["btns"]
            # 每一个增加Type
            for btn in btns:
                btn["type"] = INPUT_TYPE_SELECT
            ret.ui = StudyUIDTO("buttons",{"title":last_script.script_ui_content,"buttons":btns},lesson_id)
        elif last_script.script_ui_type == UI_TYPE_PHONE:
            ret.ui = StudyUIDTO(INPUT_TYPE_PHONE,last_script.script_ui_content,lesson_id)
        elif last_script.script_ui_type == UI_TYPE_CHECKCODE:
            expires = get_sms_code_info(app,user_id,False)
            ret.ui = StudyUIDTO(INPUT_TYPE_CHECKCODE,expires,lesson_id)
        elif last_script.script_ui_type == UI_TYPE_LOGIN:
            ret.ui = StudyUIDTO(INPUT_TYPE_LOGIN,last_script.script_ui_content,lesson_id)
        elif last_script.script_ui_type == UI_TYPE_TO_PAY:
            order =  init_buy_record(app,user_id,lesson_info.course_id,999)
            btn = [{
                        "label":last_script.script_ui_content,
                        "value":order.record_id
                    }]
            ret.ui = StudyUIDTO("order",{"title":"买课！","buttons":btn},lesson_id)
            # ret.ui = StudyUIDTO("buttons",{"title":"继续","buttons":[{"label":"继续","value":"继续"}]},last_script.lesson_id)
        
        return ret
# 重置用户信息
# 重置用户学习信息
def reset_user_study_info(app:Flask,user_id:str):
    with app.app_context():
        db.session.execute(text("delete from ai_course_buy_record where user_id = :user_id"),{"user_id":user_id})
        db.session.execute(text("delete from ai_course_lesson_attend where user_id = :user_id"),{"user_id":user_id})
        db.session.execute(text("delete from ai_course_lesson_attendscript where user_id = :user_id"),{"user_id":user_id})
        db.session.execute(text("delete from ai_course_lesson_generation where user_id = :user_id"),{"user_id":user_id})
        db.session.execute(text("delete from user_profile where user_id = :user_id"),{"user_id":user_id})
        db.session.commit()
        return True