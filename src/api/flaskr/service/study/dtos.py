# Description: This file contains the Data Transfer Objects (DTOs) for the study service.
# DTOs are used to transfer data between the service and the controller.
# @author geyunfei@gmail.com

from typing import List
from flaskr.common.swagger import register_schema_to_swagger
from flaskr.service.order.funs import AICourseLessonAttendDTO
from decimal import Decimal
import json


@register_schema_to_swagger
class ScriptDTO:
    script_type: str  # "'text' 'input' 'buttons' 'text_end'"
    script_content: str
    lesson_id: str
    script_id: str
    log_id: str

    def __init__(
        self, script_type, script_content, lesson_id, script_id=None, log_id=None
    ):
        self.script_type = script_type
        self.script_content = script_content
        self.script_id = script_id
        self.lesson_id = lesson_id
        self.log_id = log_id

    def __json__(self):
        return {
            "type": self.script_type,
            "content": self.script_content,
            "lesson_id": self.lesson_id,
            "script_id": self.script_id,
            "log_id": self.log_id,
        }

    def __str__(self):
        return json.dumps(self.__json__())


@register_schema_to_swagger
class AICourseLessonAttendScriptDTO:
    attend_id: str
    script_id: str
    lesson_id: str
    course_id: str
    user_id: str
    script_index: int
    script_role: str
    script_content: str
    status: str
    has_attend: bool

    def __init__(
        self,
        attend_id,
        script_id,
        lesson_id,
        course_id,
        user_id,
        script_index,
        script_role,
        script_content,
        status,
    ):
        self.attend_id = attend_id
        self.script_id = script_id
        self.lesson_id = lesson_id
        self.course_id = course_id
        self.user_id = user_id
        self.script_index = script_index
        self.script_role = script_role
        self.script_content = script_content
        self.status = status

    def __json__(self):
        return {
            "attend_id": self.attend_id,
            "script_id": self.script_id,
            "lesson_id": self.lesson_id,
            "course_id": self.course_id,
            "user_id": self.user_id,
            "script_index": self.script_index,
            "script_role": self.script_role,
            "script_content": self.script_content,
            "status": self.status,
        }


@register_schema_to_swagger
class AILessonAttendDTO:
    lesson_no: str
    lesson_name: str
    lesson_id: str
    status: str
    children: List[AICourseLessonAttendDTO]
    status_value: int
    updated: bool
    unique_id: str
    lesson_type: int

    def __init__(
        self,
        lesson_no: str,
        lesson_name: str,
        lesson_id: str,
        status,
        status_value,
        lesson_type: int,
        children=None,
        updated=False,
        unique_id=None,
    ) -> None:
        self.lesson_no = lesson_no
        self.lesson_name = lesson_name
        self.lesson_id = lesson_id
        self.children = children
        self.status = status
        self.status_value = status_value
        self.updated = updated
        self.unique_id = unique_id
        self.lesson_type = lesson_type

    def __json__(self):
        return {
            "lesson_no": self.lesson_no,
            "lesson_name": self.lesson_name,
            "lesson_id": self.lesson_id,
            "status": self.status,
            "status_value": self.status_value,
            "children": self.children,
            "updated": self.updated,
            "lesson_type": self.lesson_type,
        }


# @register_schema_to_swagger
class AICourseDTO:
    course_id: str
    course_name: str
    teacher_avatar: str
    course_price: Decimal
    lessons: list[AILessonAttendDTO]

    def __init__(
        self,
        course_id: str,
        course_name: str,
        teacher_avatar: str,
        course_price: Decimal,
        lessons: List[AILessonAttendDTO],
        updated: bool = False,
    ) -> None:
        self.course_id = course_id
        self.course_name = course_name
        self.teacher_avatar = teacher_avatar
        self.lessons = lessons
        self.course_price = course_price
        self.updated = updated

    def __json__(self):
        return {
            "course_id": self.course_id,
            "course_name": self.course_name,
            "teacher_avatar": self.teacher_avatar,
            "lessons": self.lessons,
            "updated": self.updated,
            "course_price": self.course_price,
        }


@register_schema_to_swagger
class StudyRecordItemDTO:
    script_index: int
    script_role: str
    script_type: int
    script_content: str
    script_id: str
    lesson_id: str
    id: str
    data: dict
    ui: dict
    interaction_type: int

    def __init__(
        self,
        script_index,
        script_role,
        script_type,
        script_content,
        script_id,
        lesson_id,
        id,
        interaction_type,
        data=None,
        ui=None,
    ):
        self.script_index = script_index
        self.script_role = script_role
        self.script_type = script_type
        self.script_content = script_content
        self.lesson_id = lesson_id
        self.script_id = script_id
        self.id = id
        self.data = data
        self.ui = ui
        self.interaction_type = interaction_type

    def __json__(self):
        ret = {
            "script_index": self.script_index,
            "script_role": self.script_role,
            "script_type": self.script_type,
            "script_content": self.script_content,
            "lesson_id": self.lesson_id,
            "id": self.id,
            "script_id": self.script_id,
            "interaction_type": self.interaction_type,
        }
        if self.data:
            ret["data"] = self.data
        if self.ui:
            ret["ui"] = self.ui
        return ret


@register_schema_to_swagger
class StudyUIDTO:
    type: str
    content: object
    lesson_id: str

    def __init__(self, type, content, lesson_id):
        self.type = type
        self.content = content
        self.lesson_id = lesson_id

    def __json__(self):
        return {"type": self.type, "content": self.content, "lesson_id": self.lesson_id}


@register_schema_to_swagger
class StudyRecordDTO:
    records: List[StudyRecordItemDTO]
    ui: ScriptDTO
    ask_mode: bool
    teacher_avatar: str
    ask_ui: ScriptDTO

    def __init__(self, records, ui=None, ask_mode=True, teacher_avatar=None):
        self.records = records
        self.ui = ui
        self.ask_mode = ask_mode
        self.teacher_avatar = teacher_avatar
        self.ask_ui = None

    def __json__(self):
        return {
            "records": self.records,
            "ui": self.ui,
            "ask_mode": self.ask_mode,
            "teacher_avatar": self.teacher_avatar,
            "ask_ui": self.ask_ui,
        }


@register_schema_to_swagger
class StudyRecordProgressDTO:
    lesson_id: str
    lesson_name: str
    lesson_no: str
    status: str
    script_index: int
    script_name: str
    is_branch: bool

    def __init__(
        self,
        lesson_id,
        lesson_name,
        lesson_no,
        status,
        script_index,
        script_name,
        is_branch,
    ):
        self.lesson_id = lesson_id
        self.lesson_name = lesson_name
        self.lesson_no = lesson_no
        self.status = status
        self.script_index = script_index
        self.script_name = script_name
        self.is_branch = is_branch

    def __json__(self):
        return {
            "lesson_id": self.lesson_id,
            "lesson_name": self.lesson_name,
            "lesson_no": self.lesson_no,
            "status": self.status,
            "script_index": self.script_index,
            "script_name": self.script_name,
            "is_branch": self.is_branch,
        }


@register_schema_to_swagger
class ScriptInfoDTO:
    script_index: int
    script_name: str
    is_trial_lesson: bool

    def __init__(self, script_index, script_name, is_trial_lesson):
        self.script_index = script_index
        self.script_name = script_name
        self.is_trial_lesson = is_trial_lesson

    def __json__(self):
        return {
            "script_index": self.script_index,
            "script_name": self.script_name,
            "is_trial_lesson": self.is_trial_lesson,
        }
