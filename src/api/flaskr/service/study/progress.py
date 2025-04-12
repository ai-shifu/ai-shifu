from flask import Flask
from .models import AICourseStudyProgress, AILessonStudyProgress
from ...service.lesson.models import AICourse, AILesson, AILessonScript
from ...service.lesson.const import LESSON_TYPE_BRANCH_HIDDEN, LESSON_TYPE_TRIAL
from ...dao import db
from ...util.uuid import generate_id
from datetime import datetime
from ...service.order.models import AICourseBuyRecord, AICourseLessonAttend
from ...service.order.consts import BUY_STATUS_SUCCESS
from ...service.order.consts import ATTEND_STATUS_COMPLETED, ATTEND_STATUS_RESET
from ...service.lesson.const import SCRIPT_TYPE_SYSTEM


class LessonInfo:
    lesson_id: str
    lesson_no: str
    lesson_type: str
    lesson_name: str
    script_count: int
    sublessons: list["LessonInfo"]

    def __init__(
        self,
        lesson_id: str,
        lesson_no: str,
        lesson_type: str,
        lesson_name: str,
        script_count: int,
        sublessons: list["LessonInfo"],
    ):
        self.lesson_id = lesson_id
        self.lesson_no = lesson_no
        self.lesson_type = lesson_type
        self.lesson_name = lesson_name
        self.script_count = script_count
        self.sublessons = sublessons

    def __str__(self):
        return f"""LessonInfo(lesson_id={self.lesson_id},
        lesson_no={self.lesson_no},
        lesson_type={self.lesson_type},
        lesson_name={self.lesson_name},
        script_count={self.script_count},
        sublessons={self.sublessons})"""

    def __repr__(self):
        return f"""LessonInfo(lesson_id={self.lesson_id},
        lesson_no={self.lesson_no},
        lesson_type={self.lesson_type},
        lesson_name={self.lesson_name},
        script_count={self.script_count},
        sublessons={self.sublessons})"""

    def __json__(self):
        return {
            "lesson_id": self.lesson_id,
            "lesson_no": self.lesson_no,
            "lesson_type": self.lesson_type,
            "lesson_name": self.lesson_name,
            "script_count": self.script_count,
            "sublessons": [i.__json__() for i in self.sublessons],
        }


# @lru_cache(maxsize=1000)
def get_course_info(course_id: str):
    lessons = AILesson.query.filter(
        AILesson.course_id == course_id,
        AILesson.lesson_type != LESSON_TYPE_BRANCH_HIDDEN,
        AILesson.status == 1,
    ).all()
    lesson_ids = [i.lesson_id for i in lessons]
    lesson_scripts = (
        AILessonScript.query.with_entities(
            AILessonScript.lesson_id, AILessonScript.script_id
        )
        .filter(
            AILessonScript.lesson_id.in_(lesson_ids),
            AILessonScript.status == 1,
            AILessonScript.script_type != SCRIPT_TYPE_SYSTEM,
        )
        .all()
    )
    lesson_script_map = {i.lesson_id: len(i) for i in lesson_scripts}
    lessons = sorted(lessons, key=lambda x: x.lesson_no)
    ret = []
    for lesson in lessons:
        if len(lesson.lesson_no) == 2:
            ret.append(
                LessonInfo(
                    lesson_id=lesson.lesson_id,
                    lesson_no=lesson.lesson_no,
                    lesson_type=lesson.lesson_type,
                    lesson_name=lesson.lesson_name,
                    script_count=lesson_script_map.get(lesson.lesson_id, 0),
                    sublessons=[],
                )
            )
        else:
            lesson_info = [i for i in ret if lesson.lesson_no.startswith(i.lesson_no)]
            if len(lesson_info) == 0:
                print(f"parent lesson not found: {lesson.lesson_no}")
                continue
            lesson_info[0].sublessons.append(
                LessonInfo(
                    lesson_id=lesson.lesson_id,
                    lesson_no=lesson.lesson_no,
                    lesson_type=lesson.lesson_type,
                    lesson_name=lesson.lesson_name,
                    script_count=lesson_script_map.get(lesson.lesson_id, 0),
                    sublessons=[],
                )
            )

    for i in ret:
        for j in i.sublessons:
            j.script_count = lesson_script_map.get(j.lesson_id, 0)
        i.script_count = sum([j.script_count for j in i.sublessons])

    return ret


def init_study_progress(app: Flask, user_id: str, course_id: str):
    with app.app_context():
        progress = AICourseStudyProgress.query.filter_by(
            user_id=user_id, course_id=course_id
        ).first()
        if not progress:
            lessons = get_course_info(course_id)
            progress_id = generate_id(app)
            progress = AICourseStudyProgress(
                progress_id=progress_id,
                user_id=user_id,
                course_id=course_id,
                chapter_count=len(lessons),
                chapter_completed_count=0,
                chapter_reset_count=0,
                is_paid=0,
                is_completed=0,
            )
            db.session.add(progress)
            for lesson in [ls for ls in lessons if ls.lesson_type == LESSON_TYPE_TRIAL]:
                lesson_progress = AILessonStudyProgress(
                    progress_id=progress_id,
                    lesson_id=lesson.lesson_id,
                    sublesson_count=len(lesson.sublessons),
                    sublesson_completed_count=0,
                    script_index=0,
                    script_count=lesson.script_count,
                )
                for sublesson in lesson.sublessons:
                    sublesson_progress = AILessonStudyProgress(
                        progress_id=progress_id,
                        lesson_id=sublesson.lesson_id,
                        sublesson_count=len(sublesson.sublessons),
                        sublesson_completed_count=0,
                        script_index=0,
                        script_count=sublesson.script_count,
                    )
                    db.session.add(sublesson_progress)
                db.session.add(lesson_progress)
            db.session.commit()


def init_study_progress_after_paid(app: Flask, user_id: str, course_id: str):
    progress = AICourseStudyProgress.query.filter_by(
        user_id=user_id, course_id=course_id
    ).first()
    if progress:
        progress.is_paid = 1
    else:
        init_study_progress(app, user_id, course_id)
        progress = AICourseStudyProgress.query.filter_by(
            user_id=user_id, course_id=course_id
        ).first()
        progress.is_paid = 1
    lessons = get_course_info(course_id)
    for lesson in lessons:
        for lesson in [ls for ls in lessons if ls.lesson_type != LESSON_TYPE_TRIAL]:
            lesson_progress = AILessonStudyProgress(
                progress_id=progress.progress_id,
                lesson_id=lesson.lesson_id,
                sublesson_count=len(lesson.sublessons),
                sublesson_completed_count=0,
                script_index=0,
                script_count=lesson.script_count,
            )
            db.session.add(lesson_progress)
            for sublesson in lesson.sublessons:
                sublesson_progress = AILessonStudyProgress(
                    progress_id=progress.progress_id,
                    lesson_id=sublesson.lesson_id,
                    sublesson_count=len(sublesson.sublessons),
                    sublesson_completed_count=0,
                    script_index=0,
                    script_count=sublesson.script_count,
                )
                db.session.add(sublesson_progress)
    db.session.flush()


class LessonProgress:
    lesson_id: str
    lesson_no: str
    lesson_type: str
    lesson_name: str
    script_count: int
    sublesson_count: int
    sublesson_completed_count: int
    script_index: int
    script_count: int
    reset_count: int
    lesson_is_updated: int
    is_completed: int
    completed_time: str
    sublessons: list["LessonProgress"]

    def __init__(
        self,
        lesson_id: str,
        lesson_no: str,
        lesson_type: str,
        lesson_name: str,
        script_count: int,
        sublesson_count: int,
        sublesson_completed_count: int,
        script_index: int,
        reset_count: int,
        lesson_is_updated: int,
        is_completed: int,
        completed_time: str,
        sublessons: list["LessonProgress"],
    ):
        self.lesson_id = lesson_id
        self.lesson_no = lesson_no
        self.lesson_type = lesson_type
        self.lesson_name = lesson_name
        self.script_count = script_count
        self.sublesson_count = sublesson_count
        self.sublesson_completed_count = sublesson_completed_count
        self.script_index = script_index
        self.reset_count = reset_count
        self.lesson_is_updated = lesson_is_updated
        self.is_completed = is_completed
        self.completed_time = completed_time
        self.sublessons = sublessons

    def __json__(self):
        return {
            "lesson_id": self.lesson_id,
            "lesson_no": self.lesson_no,
            "lesson_type": self.lesson_type,
            "lesson_name": self.lesson_name,
            "script_count": self.script_count,
            "sublesson_count": self.sublesson_count,
            "sublesson_completed_count": self.sublesson_completed_count,
            "script_index": self.script_index,
            "reset_count": self.reset_count,
            "lesson_is_updated": self.lesson_is_updated,
            "is_completed": self.is_completed,
            "completed_time": self.completed_time,
            "sublessons": [i.__json__() for i in self.sublessons],
        }


class StudyProgress:
    course_id: str
    course_name: str
    chapter_count: int
    chapter_completed_count: int
    chapter_reset_count: int
    is_paid: int
    is_completed: int
    lessons: list[LessonProgress]

    def __init__(
        self,
        course_id: str,
        course_name: str,
        chapter_count: int,
        chapter_completed_count: int,
        chapter_reset_count: int,
        is_paid: int,
        is_completed: int,
        lessons: list[LessonProgress],
    ):
        self.course_id = course_id
        self.course_name = course_name
        self.chapter_count = chapter_count
        self.chapter_completed_count = chapter_completed_count
        self.chapter_reset_count = chapter_reset_count
        self.is_paid = is_paid
        self.is_completed = is_completed
        self.lessons = lessons

    def __json__(self):
        return {
            "course_id": self.course_id,
            "course_name": self.course_name,
            "chapter_count": self.chapter_count,
            "chapter_completed_count": self.chapter_completed_count,
            "chapter_reset_count": self.chapter_reset_count,
            "is_paid": self.is_paid,
            "is_completed": self.is_completed,
            "lessons": [i.__json__() for i in self.lessons],
        }


def get_study_progress(app: Flask, user_id: str, course_id: str) -> StudyProgress:
    with app.app_context():
        progress = AICourseStudyProgress.query.filter_by(
            user_id=user_id, course_id=course_id
        ).first()
        if not progress:
            init_study_progress(app, user_id, course_id)
            progress = AICourseStudyProgress.query.filter_by(
                user_id=user_id, course_id=course_id
            ).first()
        lesson_progress = AILessonStudyProgress.query.filter_by(
            progress_id=progress.progress_id
        ).all()
        lessons_infos = AILesson.query.filter(
            AILesson.lesson_id.in_([i.lesson_id for i in lesson_progress])
        ).all()
        lesson_map = {i.lesson_id: i for i in lessons_infos}
        lessons = []
        for lesson_progress in lesson_progress:
            lesson = lesson_map.get(lesson_progress.lesson_id)
            if lesson:
                lessons.append(
                    LessonProgress(
                        lesson_id=lesson.lesson_id,
                        lesson_no=lesson.lesson_no,
                        lesson_type=lesson.lesson_type,
                        lesson_name=lesson.lesson_name,
                        sublesson_count=lesson_progress.sublesson_count,
                        sublesson_completed_count=lesson_progress.sublesson_completed_count,
                        script_index=lesson_progress.script_index,
                        script_count=lesson_progress.script_count,
                        reset_count=lesson_progress.reset_count,
                        lesson_is_updated=lesson_progress.lesson_is_updated,
                        is_completed=lesson_progress.is_completed,
                        completed_time=lesson_progress.completed_time,
                        sublessons=[],
                    )
                )

        sorted_lessons = sorted(lessons, key=lambda x: x.lesson_no)
        return_lessons = []
        for lesson in sorted_lessons:
            if len(lesson.lesson_no) == 2:
                return_lessons.append(lesson)
            else:
                return_lessons[-1].sublessons.append(lesson)
        return StudyProgress(
            course_id=course_id,
            course_name="",
            chapter_count=progress.chapter_count,
            chapter_completed_count=progress.chapter_completed_count,
            chapter_reset_count=progress.chapter_reset_count,
            is_paid=progress.is_paid,
            is_completed=progress.is_completed,
            lessons=return_lessons,
        )


def get_study_progress_by_user_id(app: Flask, user_id: str) -> list[StudyProgress]:
    with app.app_context():
        ret = []
        progress = AICourseStudyProgress.query.filter_by(user_id=user_id).all()
        if not progress:
            course_infos = AICourse.query.all()
            for course_info in course_infos:
                generate_study_progress(app, user_id, course_info.course_id)
            progress = AICourseStudyProgress.query.filter_by(user_id=user_id).all()
        lesson_progresses = AILessonStudyProgress.query.filter(
            AILessonStudyProgress.progress_id.in_([i.progress_id for i in progress])
        ).all()
        course_infos = AICourse.query.filter(
            AICourse.course_id.in_([i.course_id for i in progress])
        ).all()
        lessons_infos = AILesson.query.filter(
            AILesson.course_id.in_([i.course_id for i in course_infos])
        ).all()
        progress_map = {i.course_id: i for i in progress}
        for course_info in course_infos:
            lesson_map = {
                i.lesson_id: i
                for i in [
                    c_lesson
                    for c_lesson in lessons_infos
                    if c_lesson.course_id == course_info.course_id
                ]
            }
            lessons = []
            progress = progress_map.get(course_info.course_id, None)
            if not progress:
                continue
            for lesson_progress in [
                p for p in lesson_progresses if p.progress_id == progress.progress_id
            ]:
                lesson = lesson_map.get(lesson_progress.lesson_id)
                if lesson:
                    lessons.append(
                        LessonProgress(
                            lesson_id=lesson.lesson_id,
                            lesson_no=lesson.lesson_no,
                            lesson_type=lesson.lesson_type,
                            lesson_name=lesson.lesson_name,
                            sublesson_count=lesson_progress.sublesson_count,
                            sublesson_completed_count=lesson_progress.sublesson_completed_count,
                            script_index=lesson_progress.script_index,
                            script_count=lesson_progress.script_count,
                            reset_count=lesson_progress.reset_count,
                            lesson_is_updated=lesson_progress.lesson_is_updated,
                            is_completed=lesson_progress.is_completed,
                            completed_time=lesson_progress.completed_time,
                            sublessons=[],
                        )
                    )

            sorted_lessons = sorted(lessons, key=lambda x: x.lesson_no)
            return_lessons = []
            for lesson in sorted_lessons:
                if len(lesson.lesson_no) == 2:
                    return_lessons.append(lesson)
                else:
                    return_lessons[-1].sublessons.append(lesson)
            ret.append(
                StudyProgress(
                    course_id=course_info.course_id,
                    course_name=course_info.course_name,
                    chapter_count=progress.chapter_count,
                    chapter_completed_count=progress.chapter_completed_count,
                    chapter_reset_count=progress.chapter_reset_count,
                    is_paid=progress.is_paid,
                    is_completed=progress.is_completed,
                    lessons=return_lessons,
                )
            )
        return ret


def update_chaper_progress(
    app: Flask,
    user_id: str,
    course_id: str,
    parent_lesson_id: str,
    completed_sub_lesson_id: str,
    sub_lesson_ids: list[str],
):
    progress = AICourseStudyProgress.query.filter_by(
        user_id=user_id, course_id=course_id
    ).first()
    if not progress:
        return
    if progress.is_completed == 1:
        return
    if completed_sub_lesson_id not in sub_lesson_ids:
        return

    lesson_progress = AILessonStudyProgress.query.filter(
        AILessonStudyProgress.progress_id == progress.progress_id,
        AILessonStudyProgress.lesson_id.in_(sub_lesson_ids + [parent_lesson_id]),
    ).all()
    if len(lesson_progress) == 0:
        return
    completed_lesson_progress = [
        i for i in lesson_progress if i.lesson_id == completed_sub_lesson_id
    ]
    if len(completed_lesson_progress) == 0:
        return
    if completed_lesson_progress[0].is_completed == 1:
        return
    completed_lesson_progress[0].is_completed = 1
    completed_lesson_progress[0].completed_time = datetime.now()
    parent_lesson_progress = [
        i for i in lesson_progress if i.lesson_id == parent_lesson_id
    ]
    if len(parent_lesson_progress) == 0:
        return
    if parent_lesson_progress[0].is_completed == 1:
        return
    parent_lesson_progress[0].sublesson_completed_count = len(
        [i for i in lesson_progress if i.is_completed == 1]
    )
    if (
        parent_lesson_progress[0].sublesson_completed_count
        == parent_lesson_progress[0].sublesson_count
    ):
        parent_lesson_progress[0].is_completed = 1
        parent_lesson_progress[0].completed_time = datetime.now()
        progress.chapter_completed_count += 1
        db.session.merge(progress)
    db.session.merge(completed_lesson_progress[0])
    db.session.merge(parent_lesson_progress[0])
    db.session.flush()


def update_study_progress(
    app: Flask,
    user_id: str,
    course_id: str,
    lesson_id: str,
    script_index: int,
    is_completed: int,
    is_chapter: bool = False,
):
    progress = AICourseStudyProgress.query.filter_by(
        user_id=user_id, course_id=course_id
    ).first()
    if not progress:
        return
    lesson_progress = AILessonStudyProgress.query.filter_by(
        progress_id=progress.progress_id, lesson_id=lesson_id
    ).first()
    if not lesson_progress:
        lesson_progress = AILessonStudyProgress(
            progress_id=progress.progress_id,
            lesson_id=lesson_id,
            sublesson_count=0,
            sublesson_completed_count=0,
            script_index=script_index,
            script_count=0,
            reset_count=0,
            lesson_is_updated=0,
            is_completed=is_completed,
        )
    if lesson_progress.is_completed == 1:
        # if the lesson is completed, do not update

        return
    if is_chapter:
        progress.chapter_completed_count += 1
        if progress.chapter_completed_count == progress.chapter_count:
            progress.is_completed = 1
            progress.completed_time = datetime.now()
    else:
        lesson_progress.script_index = max(lesson_progress.script_index, script_index)
    if script_index == 1:
        lesson_progress.start_time = datetime.now()
    lesson_progress.is_completed = is_completed
    if is_completed:
        lesson_progress.completed_time = datetime.now()
        # if is_chapter == False:

    db.session.merge(lesson_progress)
    db.session.flush()


def reset_study_progress(
    app: Flask, user_id: str, course_id: str, lessons: list[AILesson]
):
    progress = AICourseStudyProgress.query.filter_by(
        user_id=user_id, course_id=course_id
    ).first()
    if not progress:
        return
    progress.chapter_reset_count += 1
    db.session.merge(progress)
    for lesson in lessons:
        lesson_progress = AILessonStudyProgress.query.filter_by(
            progress_id=progress.progress_id, lesson_id=lesson.lesson_id
        ).first()
        if lesson_progress:
            lesson_progress.reset_count += 1
            db.session.merge(lesson_progress)
    db.session.flush()


def generate_study_progress(app: Flask, user_id: str, course_id: str):
    with app.app_context():
        # 删除已存在的进度
        progress = AICourseStudyProgress.query.filter_by(
            user_id=user_id, course_id=course_id
        ).first()
        if progress:
            return
        # 查询付费状态
        buy_record = AICourseBuyRecord.query.filter(
            AICourseBuyRecord.user_id == user_id,
            AICourseBuyRecord.course_id == course_id,
            AICourseBuyRecord.status == BUY_STATUS_SUCCESS,
        ).first()
        is_paid = 1 if buy_record else 0

        # 获取历史学习记录
        attends = AICourseLessonAttend.query.filter(
            AICourseLessonAttend.user_id == user_id,
            AICourseLessonAttend.course_id == course_id,
        ).all()
        if len(attends) == 0:
            return

        attend_map = {}

        for attend in attends:
            if attend.lesson_id not in attend_map:
                attend_map[attend.lesson_id] = []
            attend_map[attend.lesson_id].append(attend)

        # 获取课程信息
        lessons = get_course_info(course_id)
        progress_id = generate_id(app)

        # 创建课程进度
        progress = AICourseStudyProgress(
            progress_id=progress_id,
            user_id=user_id,
            course_id=course_id,
            chapter_count=len(lessons),
            chapter_completed_count=0,
            chapter_reset_count=0,
            is_paid=is_paid,
            is_completed=0,
            created=min([attend.created for attend in attends]),
            updated=datetime.now(),
        )
        db.session.add(progress)

        # 根据是否付费决定要生成的课程范围
        target_lessons = (
            lessons
            if is_paid
            else [ls for ls in lessons if ls.lesson_type == LESSON_TYPE_TRIAL]
        )

        completed_chapter_count = 0

        # 为每个课程创建进度
        for lesson in target_lessons:
            lesson_attends = attend_map.get(lesson.lesson_id, [])
            is_completed = (
                1
                if [
                    attend
                    for attend in lesson_attends
                    if attend.status == ATTEND_STATUS_COMPLETED
                ]
                else 0
            )

            if is_completed:
                completed_chapter_count += 1

            lesson_progress = AILessonStudyProgress(
                progress_id=progress_id,
                lesson_id=lesson.lesson_id,
                sublesson_count=len(lesson.sublessons),
                sublesson_completed_count=0,
                script_index=max(
                    [attend.script_index for attend in lesson_attends], default=0
                ),
                script_count=lesson.script_count,
                reset_count=len(
                    [
                        attend
                        for attend in lesson_attends
                        if attend.status == ATTEND_STATUS_RESET
                    ]
                ),
                lesson_is_updated=0,
                is_completed=is_completed,
                end_time=(
                    max([attend.updated for attend in lesson_attends])
                    if is_completed
                    else None
                ),
                begin_time=(
                    min([attend.created for attend in lesson_attends])
                    if is_completed
                    else None
                ),
            )
            db.session.add(lesson_progress)

            completed_sublesson_count = 0
            # 为子课程创建进度
            for sublesson in lesson.sublessons:
                sublesson_attends = attend_map.get(sublesson.lesson_id, [])
                if len(sublesson_attends) == 0:
                    continue
                script_index = max(
                    [attend.script_index for attend in sublesson_attends], default=0
                )
                is_completed = (
                    1
                    if [
                        attend
                        for attend in sublesson_attends
                        if attend.status == ATTEND_STATUS_COMPLETED
                    ]
                    else 0
                )
                if is_completed:
                    completed_sublesson_count += 1
                sublesson_progress = AILessonStudyProgress(
                    progress_id=progress_id,
                    lesson_id=sublesson.lesson_id,
                    sublesson_count=len(sublesson.sublessons),
                    sublesson_completed_count=0,
                    script_index=script_index,
                    script_count=sublesson.script_count,
                    reset_count=len(
                        [
                            attend
                            for attend in sublesson_attends
                            if attend.status == ATTEND_STATUS_RESET
                        ]
                    ),
                    lesson_is_updated=0,
                    is_completed=is_completed,
                    end_time=(
                        max([attend.updated for attend in sublesson_attends])
                        if is_completed
                        else None
                    ),
                    begin_time=min([attend.created for attend in sublesson_attends]),
                )
                db.session.add(sublesson_progress)

            # 更新父课程的完成子课程数
            lesson_progress.sublesson_completed_count = completed_sublesson_count
            if completed_sublesson_count == len(lesson.sublessons):
                lesson_progress.is_completed = 1
                lesson_progress.completed_time = max(
                    [attend.updated for attend in lesson_attends]
                )
            db.session.merge(lesson_progress)
        # 更新课程总进度
        progress.chapter_completed_count = completed_chapter_count
        if completed_chapter_count == len(target_lessons):
            progress.is_completed = 1
            progress.completed_time = max([attend.updated for attend in attends])
        db.session.merge(progress)
        db.session.commit()
