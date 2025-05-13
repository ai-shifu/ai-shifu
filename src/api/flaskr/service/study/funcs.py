from flask import Flask

from flaskr.dao import run_with_redis
from flaskr.framework.plugin.plugin_manager import extensible
from flaskr.service.study.const import (
    ROLE_VALUES,
)
from ...service.study.dtos import AILessonAttendDTO, StudyRecordDTO
import json
from ...service.order.consts import (
    ATTEND_STATUS_BRANCH,
    ATTEND_STATUS_LOCKED,
    ATTEND_STATUS_NOT_STARTED,
    ATTEND_STATUS_COMPLETED,
    ATTEND_STATUS_IN_PROGRESS,
    ATTEND_STATUS_RESET,
    get_attend_status_values,
    BUY_STATUS_SUCCESS,
)

from .dtos import AICourseDTO, StudyRecordItemDTO, StudyRecordProgressDTO, ScriptInfoDTO
from ...service.lesson.const import (
    LESSON_TYPE_BRANCH_HIDDEN,
    LESSON_TYPE_NORMAL,
    LESSON_TYPE_TRIAL,
    STATUS_PUBLISH,
)
from ...dao import db

from ...service.lesson.models import AICourse, AILesson, AILessonScript
from ...service.order.models import (
    AICourseBuyRecord,
    AICourseLessonAttend,
)
from ...service.common.models import raise_error
from .models import AICourseLessonAttendScript, AICourseAttendAsssotion
from .plugin import handle_ui
from flaskr.api.langfuse import MockClient
from flaskr.util.uuid import generate_id
from flaskr.service.user.models import User


def get_lesson_tree_to_study_inner(
    app: Flask, user_id: str, course_id: str = None
) -> AICourseDTO:
    with app.app_context():

        app.logger.info("user_id:" + user_id)
        attend_status_values = get_attend_status_values()
        if course_id:
            course_info = (
                AICourse.query.filter(
                    AICourse.course_id == course_id,
                    AICourse.status.in_([STATUS_PUBLISH]),
                )
                .order_by(AICourse.id.desc())
                .first()
            )
            if not course_info:
                raise_error("LESSON.COURSE_NOT_FOUND")
        else:
            course_info = AICourse.query.order_by(AICourse.id.asc()).first()
            if not course_info:
                raise_error("LESSON.HAS_NOT_LESSON")
            course_id = course_info.course_id
        buy_record = AICourseBuyRecord.query.filter_by(
            user_id=user_id, course_id=course_id
        ).first()
        paid = False
        if buy_record:
            paid = buy_record.status == BUY_STATUS_SUCCESS

        lessons = (
            AILesson.query.filter(
                AILesson.course_id == course_id,
                AILesson.lesson_type != LESSON_TYPE_BRANCH_HIDDEN,
                AILesson.status == 1,
            )
            .order_by(AILesson.id.desc())
            .all()
        )

        online_lessons = [i for i in lessons if i.status == 1]
        online_lessons = sorted(
            online_lessons, key=lambda x: (len(x.lesson_no), x.lesson_no)
        )
        old_lessons = [i for i in lessons if i.status != 1]
        old_lessons = sorted(old_lessons, key=lambda x: x.id, reverse=True)

        lesson_map = {i.lesson_id: i for i in online_lessons}

        attend_infos = AICourseLessonAttend.query.filter(
            AICourseLessonAttend.user_id == user_id,
            AICourseLessonAttend.course_id == course_id,
            AICourseLessonAttend.status != ATTEND_STATUS_RESET,
        ).all()
        updated_attend = False

        app.logger.info("attend_infos:{}".format(len(attend_infos)))
        # init the attend info for the trial lessons

        is_first_chapter = False
        is_first_lesson = False

        if len(attend_infos) == 0:
            app.logger.info(
                "init the attend info for the trial lessons,user_id:{} course_id:{}".format(
                    user_id, course_id
                )
            )
            for lesson in [
                online_lesson
                for online_lesson in online_lessons
                if online_lesson.lesson_type == LESSON_TYPE_TRIAL
            ]:

                status = ATTEND_STATUS_LOCKED

                if len(lesson.lesson_no) == 2 and not is_first_chapter:
                    is_first_chapter = True
                    status = ATTEND_STATUS_NOT_STARTED
                if len(lesson.lesson_no) == 4 and not is_first_lesson:
                    is_first_lesson = True
                    status = ATTEND_STATUS_NOT_STARTED
                app.logger.info(
                    "lesson_no:{},status:{}".format(lesson.lesson_no, status)
                )
                attend_info = AICourseLessonAttend(
                    attend_id=generate_id(app),
                    user_id=user_id,
                    lesson_id=lesson.lesson_id,
                    course_id=lesson.course_id,
                    status=status,
                )
                attend_infos.append(attend_info)
                db.session.add(attend_info)
                updated_attend = True

        attend_map = {i.lesson_id: i for i in attend_infos}
        lessonInfos = []
        lesson_dict = {}
        app.logger.info(
            "online_lessons:{}".format([i.lesson_no for i in online_lessons])
        )
        # init the lesson info
        for lesson in online_lessons:
            if lesson_dict.get(lesson.lesson_no, None) is None:
                attend_info = attend_map.get(lesson.lesson_id, None)
                status = attend_info.status if attend_info else ATTEND_STATUS_LOCKED
                lesson_dict[lesson.lesson_no] = AILessonAttendDTO(
                    lesson.lesson_no,
                    lesson.lesson_name,
                    lesson.lesson_id,
                    attend_status_values[status],
                    status,
                    lesson.lesson_type,
                    [],
                    unique_id=lesson.lesson_feishu_id,
                    updated=(
                        True
                        if attend_info and attend_info.lesson_updated == 1
                        else False
                    ),
                )
        # init the lesson tree
        for key in lesson_dict:
            if len(lesson_dict[key].lesson_no) == 2:
                lessonInfos.append(lesson_dict[key])
            else:
                parent_no = key[:-2]
                if parent_no in lesson_dict:
                    lesson_dict[parent_no].children.append(lesson_dict[key])
                    lesson_dict[parent_no].updated = (
                        lesson_dict[parent_no].updated or lesson_dict[key].updated
                    )
        for lesson in lessonInfos:
            lesson.children = sorted(
                lesson.children, key=lambda x: (len(x.lesson_no), x.lesson_no)
            )

        for lesson_index, lesson in enumerate(lessonInfos):
            attend_info = attend_map.get(lesson.lesson_id, None)
            if attend_info is None:
                lesson_info = lesson_map.get(lesson.lesson_id, None)
                if lesson_info and lesson_info.lesson_type == LESSON_TYPE_NORMAL:
                    if not paid:
                        continue
                old_lesson_infos = [
                    i
                    for i in old_lessons
                    if i.lesson_feishu_id == lesson.unique_id
                    and len(i.lesson_no) == len(lesson.lesson_no)
                ]
                if len(old_lesson_infos) > 0:
                    attend_info = attend_map.get(old_lesson_infos[0].lesson_id, None)
                    if attend_info:
                        lesson.status_value = attend_info.status
                        lesson.status = attend_status_values[attend_info.status]
                        lesson.updated = True
                        lessonInfos[lesson_index] = lesson
                        attend_info.lesson_id = lesson.lesson_id
                        attend_info.lesson_updated = 1
                        app.logger.info(
                            "update attend info from lesson:{} to lesson:{}".format(
                                attend_info.lesson_id, lesson.lesson_id
                            )
                        )
                        attend_map[old_lesson_infos[0].lesson_id] = attend_info
                        updated_attend = True

            for i, child in enumerate(lesson.children):
                attend_info = attend_map.get(child.lesson_id, None)
                if attend_info:
                    continue
                is_updated_old_to_now = False
                old_lesson_infos = [
                    i
                    for i in old_lessons
                    if i.lesson_feishu_id == child.unique_id
                    and len(i.lesson_no) == len(child.lesson_no)
                ]
                app.logger.info(
                    "old_lessons:{}".format([i.lesson_no for i in old_lesson_infos])
                )
                if len(old_lesson_infos) > 0:
                    for old_lesson in old_lesson_infos:
                        if old_lesson.lesson_no[-2:] == child.lesson_no[-2:] and len(
                            old_lesson.lesson_no
                        ) == len(child.lesson_no):
                            old_attend_info = attend_map.get(old_lesson.lesson_id, None)
                            if (
                                old_attend_info
                                and old_attend_info.status != ATTEND_STATUS_BRANCH
                            ):
                                # update old attend info lesson_id to now lesson_id
                                child.status_value = old_attend_info.status
                                child.status = attend_status_values[
                                    old_attend_info.status
                                ]
                                child.updated = True
                                lesson.children[i] = child
                                old_attend_info.lesson_id = child.lesson_id
                                old_attend_info.lesson_updated = 1
                                attend_map[old_lesson.lesson_id] = old_attend_info
                                updated_attend = True
                                is_updated_old_to_now = True
                                app.logger.info(
                                    "update attend info from lesson:{} to lesson:{}".format(
                                        old_attend_info.lesson_id, child.lesson_id
                                    )
                                )
                                break
                if not is_updated_old_to_now:
                    attend_info = AICourseLessonAttend(
                        attend_id=generate_id(app),
                        user_id=user_id,
                        lesson_id=child.lesson_id,
                        course_id=course_id,
                        status=ATTEND_STATUS_LOCKED,
                    )
                    app.logger.info(
                        "add attend info for lesson:{},lesson_no:{}".format(
                            child.lesson_id, child.lesson_no
                        )
                    )
                    db.session.add(attend_info)
                    attend_map[lesson.lesson_id] = attend_info
                    updated_attend = True

        if updated_attend:
            app.logger.info("commit the attend info")
            db.session.commit()

        for lesson_index, lessonInfo in enumerate(lessonInfos):
            is_completed = True
            for i, child in enumerate(lessonInfo.children):
                if child.status_value == ATTEND_STATUS_BRANCH:
                    child.status_value = ATTEND_STATUS_IN_PROGRESS
                    child.status = attend_status_values[ATTEND_STATUS_IN_PROGRESS]
                    lessonInfo.children[i] = child
                    lessonInfo.updated = True
                    lessonInfos[lesson_index] = lessonInfo
                if child.status_value == ATTEND_STATUS_IN_PROGRESS:
                    lessonInfo.status_value = ATTEND_STATUS_IN_PROGRESS
                    lessonInfo.status = attend_status_values[ATTEND_STATUS_IN_PROGRESS]
                    lessonInfos[lesson_index] = lessonInfo
                is_completed = (
                    is_completed and child.status_value == ATTEND_STATUS_COMPLETED
                )
            if is_completed:
                lessonInfo.status_value = ATTEND_STATUS_COMPLETED
                lessonInfo.status = attend_status_values[ATTEND_STATUS_COMPLETED]
                lessonInfos[lesson_index] = lessonInfo

        ret = AICourseDTO(
            course_id=course_info.course_id,
            course_name=course_info.course_name,
            teach_avator=course_info.course_teacher_avator,
            course_price=course_info.course_price,
            lessons=lessonInfos,
        )
        return ret


@extensible
def get_lesson_tree_to_study(
    app: Flask, user_id: str, course_id: str = None
) -> AICourseDTO:
    return run_with_redis(
        app,
        app.config.get("REDIS_KEY_PREFIX") + ":get_lesson_tree_to_study:" + user_id,
        5,
        get_lesson_tree_to_study_inner,
        [app, user_id, course_id],
    )


@extensible
def get_study_record(app: Flask, user_id: str, lesson_id: str) -> StudyRecordDTO:
    with app.app_context():
        lesson_info = (
            AILesson.query.filter(
                AILesson.lesson_id == lesson_id,
                AILesson.status == 1,
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        course_info = AICourse.query.filter_by(course_id=lesson_info.course_id).first()
        if not course_info:
            return None
        teach_avator = course_info.course_teacher_avator
        lesson_ids = [lesson_id]
        if not lesson_info:
            return None
        if len(lesson_info.lesson_no) <= 2:
            lesson_infos = (
                AILesson.query.filter(
                    AILesson.lesson_no.like(lesson_info.lesson_no + "%"),
                    AILesson.status == 1,
                    AILesson.course_id == lesson_info.course_id,
                )
                .order_by(AILesson.id.desc())
                .all()
            )
            lesson_ids = [lesson.lesson_id for lesson in lesson_infos]
        attend_infos = (
            AICourseLessonAttend.query.filter(
                AICourseLessonAttend.user_id == user_id,
                AICourseLessonAttend.lesson_id.in_(lesson_ids),
                AICourseLessonAttend.course_id == lesson_info.course_id,
                AICourseLessonAttend.status != ATTEND_STATUS_RESET,
            )
            .order_by(AICourseLessonAttend.id)
            .all()
        )
        if not attend_infos:
            return None
        attend_ids = [attend_info.attend_id for attend_info in attend_infos]
        attend_scripts = (
            AICourseLessonAttendScript.query.filter(
                AICourseLessonAttendScript.attend_id.in_(attend_ids)
            )
            .order_by(AICourseLessonAttendScript.id.asc())
            .all()
        )
        if len(attend_scripts) == 0:
            return StudyRecordDTO([])
        items = [
            StudyRecordItemDTO(
                i.script_index,
                ROLE_VALUES[i.script_role],
                0,
                i.script_content,
                i.script_id,
                i.lesson_id if i.lesson_id in lesson_ids else lesson_id,
                i.log_id,
                i.interaction_type,
                ui=json.loads(i.script_ui_conf) if i.script_ui_conf else None,
            )
            for i in attend_scripts
        ]
        user_info = User.query.filter_by(user_id=user_id).first()
        ret = StudyRecordDTO(items, teach_avator=teach_avator)
        last_script_id = attend_scripts[-1].script_id
        last_script = (
            AILessonScript.query.filter(
                AILessonScript.script_id == last_script_id,
                AILessonScript.status == 1,
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
        if last_script is None:
            ret.ui = []
            return ret
        last_lesson_id = last_script.lesson_id
        lesson_id = last_lesson_id
        last_attends = [i for i in attend_infos if i.lesson_id == last_lesson_id]
        if len(last_attends) == 0:
            last_attend = (
                AICourseLessonAttend.query.filter(
                    AICourseLessonAttend.user_id == user_id,
                    AICourseLessonAttend.lesson_id == last_lesson_id,
                    AICourseLessonAttend.status != ATTEND_STATUS_RESET,
                )
                .order_by(AICourseLessonAttend.id.desc())
                .first()
            )
            if last_attend is None:
                pass
        else:
            last_attend = last_attends[-1]
        if last_attend is None or last_attend.status == ATTEND_STATUS_COMPLETED:
            app.logger.info(
                "last_script.script_ui_content:{}".format(last_script.script_ui_content)
            )
            uis = handle_ui(
                app, user_info, last_attend, last_script, "", MockClient(), {}
            )
            app.logger.info("uis:{}".format(uis))
            if len(uis) > 0:
                ret.ui = uis[0]
            return ret

        uis = handle_ui(app, user_info, last_attend, last_script, "", MockClient(), {})
        app.logger.info("uis:{}".format(uis))
        if len(uis) > 0:
            ret.ui = uis[0]

        if len(uis) > 1:
            ret.ask_mode = uis[1].script_content.get("ask_mode", False)
            ret.ask_ui = uis[1]
        return ret


@extensible
def get_lesson_study_progress(
    app: Flask, user_id: str, lesson_id: str
) -> StudyRecordProgressDTO:
    with app.app_context():
        attend_status_values = get_attend_status_values()
        lesson_info = (
            AILesson.query.filter(
                AILesson.lesson_id == lesson_id,
                AILesson.status == 1,
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        if not lesson_info:
            return None
        attend_info = (
            AICourseLessonAttend.query.filter(
                AICourseLessonAttend.user_id == user_id,
                AICourseLessonAttend.lesson_id == lesson_id,
                AICourseLessonAttend.status != ATTEND_STATUS_RESET,
            )
            .order_by(AICourseLessonAttend.id.desc())
            .first()
        )
        if not attend_info:
            return None

        lesson_no = lesson_info.lesson_no
        lesson_name = lesson_info.lesson_name
        script_index = 0
        script_name = ""
        is_branch = False
        while attend_info is not None and attend_info.status == ATTEND_STATUS_BRANCH:
            script_index = script_index + attend_info.script_index
            is_branch = True
            associaions = AICourseAttendAsssotion.query.filter_by(
                user_id=user_id, from_attend_id=attend_info.attend_id
            ).first()
            if associaions:
                attend_info = AICourseLessonAttend.query.filter_by(
                    attend_id=associaions.to_attend_id
                ).first()

        if attend_info is None:
            return None

        script_info = (
            AILessonScript.query.filter(
                AILessonScript.lesson_id == attend_info.lesson_id,
                AILessonScript.script_index == attend_info.script_index,
                AILessonScript.status == 1,
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
        if script_info is None:
            return None

        script_name = script_info.script_name
        return StudyRecordProgressDTO(
            lesson_id,
            lesson_name,
            lesson_no,
            attend_status_values[attend_info.status],
            script_index,
            script_name,
            is_branch,
        )


# get script info
@extensible
def get_script_info(app: Flask, user_id: str, script_id: str) -> ScriptInfoDTO:
    with app.app_context():
        script_info = (
            AILessonScript.query.filter(
                AILessonScript.script_id == script_id,
                AILessonScript.status == 1,
            )
            .order_by(AILessonScript.id.desc())
            .first()
        )
        if not script_info:
            return None
        lesson = (
            AILesson.query.filter(
                AILesson.lesson_id == script_info.lesson_id,
                AILesson.status == 1,
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        if not lesson:
            return None
        return ScriptInfoDTO(
            script_info.script_index,
            script_info.script_name,
            lesson.lesson_type == LESSON_TYPE_TRIAL,
        )


# reset user study info by lesson
@extensible
def reset_user_study_info_by_lesson(app: Flask, user_id: str, lesson_id: str):
    with app.app_context():
        lesson_info = (
            AILesson.query.filter(
                AILesson.lesson_id == lesson_id,
                AILesson.status == 1,
            )
            .order_by(AILesson.id.desc())
            .first()
        )
        if not lesson_info:
            app.logger.info("lesson_info not found")
            return False
        lesson_no = lesson_info.lesson_no
        course_id = lesson_info.course_id
        if len(lesson_no) > 2:
            raise_error("LESSON.LESSON_CANNOT_BE_RESET")
        lessons = (
            AILesson.query.filter(
                AILesson.lesson_no.like(lesson_no + "%"),
                AILesson.status == 1,
                AILesson.course_id == course_id,
            )
            .order_by(AILesson.id.desc())
            .all()
        )
        lesson_ids = [lesson.lesson_id for lesson in lessons]
        attend_infos = AICourseLessonAttend.query.filter(
            AICourseLessonAttend.user_id == user_id,
            AICourseLessonAttend.lesson_id.in_(lesson_ids),
            AICourseLessonAttend.status != ATTEND_STATUS_RESET,
            AICourseLessonAttend.course_id == course_id,
        ).all()
        attend_ids = [attend_info.attend_id for attend_info in attend_infos]
        attend_assositions = AICourseAttendAsssotion.query.filter(
            AICourseAttendAsssotion.from_attend_id.in_(attend_ids)
        ).all()
        to_attend_ids = [
            attend_assosition.to_attend_id for attend_assosition in attend_assositions
        ]
        if len(to_attend_ids) > 0:
            AICourseLessonAttend.query.filter(
                AICourseLessonAttend.attend_id.in_(to_attend_ids)
            ).update({"status": ATTEND_STATUS_RESET})
        # reset the attend info
        for attend_info in attend_infos:
            attend_info.status = ATTEND_STATUS_RESET
        # insert the new attend info for the lessons that are available
        for lesson in [lesson for lesson in lessons if lesson.status == 1]:
            attend_info = AICourseLessonAttend(
                user_id=user_id,
                lesson_id=lesson.lesson_id,
                course_id=lesson.course_id,
                status=ATTEND_STATUS_LOCKED,
                script_index=0,
            )
            attend_info.attend_id = generate_id(app)
            if lesson.lesson_no == lesson_no:
                attend_info.status = ATTEND_STATUS_IN_PROGRESS
            if lesson.lesson_no == lesson_no + "01":
                attend_info.status = ATTEND_STATUS_IN_PROGRESS
            db.session.add(attend_info)
        db.session.commit()
        return True


@extensible
def set_script_content_operation(
    app: Flask, user_id: str, log_id: str, interaction_type: int
):
    with app.app_context():
        script_info = AICourseLessonAttendScript.query.filter(
            AICourseLessonAttendScript.log_id == log_id,
            AICourseLessonAttendScript.user_id == user_id,
        ).first()
        if not script_info:
            return None
        # update the script_info
        script_info.interaction_type = interaction_type
        db.session.merge(script_info)
        db.session.commit()
        return True
