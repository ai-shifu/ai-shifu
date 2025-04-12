import traceback
from typing import Generator
from flask import Flask

from flaskr.service.common.models import AppException, raise_error
from flaskr.service.user.models import User
from flaskr.i18n import _
from ...api.langfuse import langfuse_client as langfuse
from ...service.lesson.const import (
    LESSON_TYPE_TRIAL,
)
from ...service.lesson.models import AICourse, AILesson
from ...service.order.consts import (
    ATTEND_STATUS_BRANCH,
    ATTEND_STATUS_COMPLETED,
    ATTEND_STATUS_IN_PROGRESS,
    ATTEND_STATUS_NOT_STARTED,
    ATTEND_STATUS_RESET,
    ATTEND_STATUS_LOCKED,
    get_attend_status_values,
)
from ...service.order.funs import (
    AICourseLessonAttendDTO,
    init_trial_lesson,
    init_trial_lesson_inner,
)
from ...service.order.models import AICourseLessonAttend
from ...service.study.const import (
    INPUT_TYPE_ASK,
    INPUT_TYPE_START,
    INPUT_TYPE_CONTINUE,
)
from ...service.study.dtos import ScriptDTO
from ...dao import db, redis_client
from .utils import (
    make_script_dto,
    get_script,
    update_lesson_status,
    get_current_lesson,
    check_script_is_last_script,
)
from .input_funcs import BreakException
from .output_funcs import handle_output
from .plugin import handle_input, handle_ui, check_continue
from .utils import make_script_dto_to_stream
from flaskr.service.study.dtos import AILessonAttendDTO


def run_script_inner(
    app: Flask,
    user_id: str,
    course_id: str,
    lesson_id: str = None,
    input: str = None,
    input_type: str = None,
    script_id: str = None,
    log_id: str = None,
) -> Generator[str, None, None]:
    with app.app_context():
        script_info = None
        attend = None
        lesson_info = None
        course_info = None
        
        try:
            with db.session.begin_nested():
                app.logger.info(f"Starting run_script_inner for user {user_id}")
                attend_status_values = get_attend_status_values()
                user_info = User.query.filter(User.user_id == user_id).first()
                db.session.commit()
            
            if not lesson_id:
                app.logger.info("lesson_id is None, initializing trial lesson")
                
                with db.session.begin_nested():
                    if course_id:
                        course_info = AICourse.query.filter(
                            AICourse.course_id == course_id,
                            AICourse.status == 1,
                        ).first()
                    else:
                        course_info = AICourse.query.filter(
                            AICourse.status == 1,
                        ).first()
                        if course_info is None:
                            raise_error("LESSON.HAS_NOT_LESSON")
                    
                    if not course_info:
                        raise_error("LESSON.COURSE_NOT_FOUND")
                    
                    course_id = course_info.course_id
                    db.session.commit()
                
                yield make_script_dto(
                    "teacher_avator", course_info.course_teacher_avator, ""
                )
                
                with db.session.begin_nested():
                    lessons = init_trial_lesson(app, user_id, course_id)
                    attend = get_current_lesson(app, lessons)
                    lesson_id = attend.lesson_id
                    lesson_info = AILesson.query.filter(
                        AILesson.lesson_id == lesson_id,
                    ).first()
                    if not lesson_info:
                        raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
                    db.session.commit()
            else:
                with db.session.begin_nested():
                    lesson_info = AILesson.query.filter(
                        AILesson.lesson_id == lesson_id,
                    ).first()
                    if not lesson_info:
                        raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
                    course_id = lesson_info.course_id
                    db.session.commit()
                app.logger.info(
                    "user_id:{},course_id:{},lesson_id:{},lesson_no:{}".format(
                        user_id, course_id, lesson_id, lesson_info.lesson_no
                    )
                )
                
                with db.session.begin_nested():
                    course_info = AICourse.query.filter(
                        AICourse.course_id == course_id,
                        AICourse.status == 1,
                    ).first()
                    if not course_info:
                        raise_error("LESSON.COURSE_NOT_FOUND")
                    db.session.commit()
                
                yield make_script_dto(
                    "teacher_avator", course_info.course_teacher_avator, ""
                )
                
                attend_info = None
                with db.session.begin_nested():
                    attend_info = AICourseLessonAttend.query.filter(
                        AICourseLessonAttend.user_id == user_id,
                        AICourseLessonAttend.course_id == course_id,
                        AICourseLessonAttend.lesson_id == lesson_id,
                        AICourseLessonAttend.status != ATTEND_STATUS_RESET,
                    ).first()
                    db.session.commit()
                if not attend_info:
                    if lesson_info.lesson_type == LESSON_TYPE_TRIAL:
                        app.logger.info(
                            "init trial lesson for user:{} course:{}".format(
                                user_id, course_id
                            )
                        )
                        with db.session.begin_nested():
                            new_attend_infos = init_trial_lesson_inner(
                                app, user_id, course_id
                            )
                            new_attend_maps = {i.lesson_id: i for i in new_attend_infos}
                            attend_info = new_attend_maps.get(lesson_id, None)
                            if not attend_info:
                                raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
                            db.session.commit()
                    else:
                        raise_error("COURSE.COURSE_NOT_PURCHASED")

                if (
                    attend_info.status == ATTEND_STATUS_COMPLETED
                    or attend_info.status == ATTEND_STATUS_LOCKED
                ):
                    parent_no = lesson_info.lesson_no
                    lessons = []
                    lesson_ids = []
                    
                    with db.session.begin_nested():
                        if len(parent_no) >= 2:
                            parent_no = parent_no[:-2]
                        lessons = AILesson.query.filter(
                            AILesson.lesson_no.like(parent_no + "__"),
                            AILesson.course_id == course_id,
                            AILesson.status == 1,
                        ).all()
                        lesson_ids = [lesson.lesson_id for lesson in lessons]
                        db.session.commit()
                    
                    app.logger.info(
                        "study lesson no :{}".format(
                            ",".join([lesson.lesson_no for lesson in lessons])
                        )
                    )
                    
                    attend_infos = []
                    with db.session.begin_nested():
                        attend_infos = AICourseLessonAttend.query.filter(
                            AICourseLessonAttend.user_id == user_id,
                            AICourseLessonAttend.course_id == course_id,
                            AICourseLessonAttend.lesson_id.in_(lesson_ids),
                            AICourseLessonAttend.status.in_(
                                [
                                    ATTEND_STATUS_NOT_STARTED,
                                    ATTEND_STATUS_IN_PROGRESS,
                                    ATTEND_STATUS_BRANCH,
                                ]
                            ),
                        ).all()
                        db.session.commit()
                    
                    attend_maps = {i.lesson_id: i for i in attend_infos}
                    lessons = sorted(lessons, key=lambda x: x.lesson_no)
                    for lesson in lessons:
                        lesson_attend_info = attend_maps.get(lesson.lesson_id, None)
                        if (
                            len(lesson.lesson_no) > 2
                            and lesson_attend_info
                            and lesson_attend_info.status
                            in [
                                ATTEND_STATUS_NOT_STARTED,
                                ATTEND_STATUS_IN_PROGRESS,
                                ATTEND_STATUS_BRANCH,
                            ]
                        ):
                            lesson_id = lesson_attend_info.lesson_id
                            attend_info = lesson_attend_info
                            break
                attend = AICourseLessonAttendDTO(
                    attend_info.attend_id,
                    attend_info.lesson_id,
                    attend_info.course_id,
                    attend_info.user_id,
                    attend_info.status,
                    attend_info.script_index,
                )
                
                db.session.commit()
                
                trace_args = {}
                trace_args["user_id"] = user_id
                trace_args["session_id"] = attend.attend_id
                trace_args["input"] = input
                trace_args["name"] = course_info.course_name
                trace = langfuse.trace(**trace_args)
                trace_args["output"] = ""
                next = 0
                is_first_add = False
                
                with db.session.begin_nested():
                    script_info, attend_updates, is_first_add = get_script(
                        app, attend_id=attend.attend_id, next=next
                    )
                    db.session.commit()
            auto_next_lesson_id = None
            next_chapter_no = None
            
            if len(attend_updates) > 0:
                app.logger.info(f"attend_updates: {attend_updates}")
                for attend_update in attend_updates:
                    if len(attend_update.lesson_no) > 2:
                        yield make_script_dto(
                            "lesson_update", attend_update.__json__(), ""
                        )
                        if next_chapter_no and attend_update.lesson_no.startswith(
                            next_chapter_no
                        ):
                            auto_next_lesson_id = attend_update.lesson_id
                    else:
                        yield make_script_dto(
                            "chapter_update", attend_update.__json__(), ""
                        )
                        if (
                            attend_update.status
                            == attend_status_values[ATTEND_STATUS_NOT_STARTED]
                        ):
                            yield make_script_dto(
                                "next_chapter", attend_update.__json__(), ""
                            )
                            next_chapter_no = attend_update.lesson_no

            app.logger.info(f"lesson_info: {lesson_info}")
            
            if script_info:
                try:
                    response = handle_input(
                        app,
                        user_info,
                        input_type,
                        lesson_info,
                        attend,
                        script_info,
                        input,
                        trace,
                        trace_args,
                    )
                    if response:
                        yield from response
                    
                    if input_type == INPUT_TYPE_START:
                        next = 0
                    else:
                        next = 1
                    
                    while True and input_type != INPUT_TYPE_ASK:
                        if is_first_add:
                            is_first_add = False
                            next = 0
                        
                        with db.session.begin_nested():
                            script_info, attend_updates, _ = get_script(
                                app, attend_id=attend.attend_id, next=next
                            )
                            db.session.commit()
                        
                        next = 1
                        
                        if len(attend_updates) > 0:
                            for attend_update in attend_updates:
                                if len(attend_update.lesson_no) > 2:
                                    yield make_script_dto(
                                        "lesson_update", attend_update.__json__(), ""
                                    )
                                else:
                                    yield make_script_dto(
                                        "chapter_update", attend_update.__json__(), ""
                                    )
                                    if (
                                        attend_update.status
                                        == attend_status_values[
                                            ATTEND_STATUS_NOT_STARTED
                                        ]
                                    ):
                                        yield make_script_dto(
                                            "next_chapter", attend_update.__json__(), ""
                                        )
                        
                        if script_info:
                            response = handle_output(
                                app,
                                user_id,
                                lesson_info,
                                attend,
                                script_info,
                                input,
                                trace,
                                trace_args,
                            )
                            if response:
                                yield from response

                            if check_continue(
                                app,
                                user_info,
                                attend,
                                script_info,
                                input,
                                trace,
                                trace_args,
                            ):
                                app.logger.info(f"check_continue: {script_info}")
                                next = 1
                                input_type = INPUT_TYPE_CONTINUE
                                continue
                            else:
                                break
                        else:
                            break
                    if script_info and not check_script_is_last_script(
                        app, script_info, lesson_info
                    ):
                        script_dtos = handle_ui(
                            app,
                            user_info,
                            attend,
                            script_info,
                            input,
                            trace,
                            trace_args,
                        )
                        for script_dto in script_dtos:
                            yield make_script_dto_to_stream(script_dto)
                    else:
                        res = None
                        with db.session.begin_nested():
                            res = update_lesson_status(app, attend.attend_id)
                            db.session.commit()
                        
                        if res:
                            for attend_update in res:
                                if isinstance(attend_update, AILessonAttendDTO):
                                    if len(attend_update.lesson_no) > 2:
                                        yield make_script_dto(
                                            "lesson_update",
                                            attend_update.__json__(),
                                            "",
                                        )
                                        if (
                                            next_chapter_no
                                            and attend_update.lesson_no.startswith(
                                                next_chapter_no
                                            )
                                        ):
                                            auto_next_lesson_id = (
                                                attend_update.lesson_id
                                            )
                                    else:
                                        yield make_script_dto(
                                            "chapter_update",
                                            attend_update.__json__(),
                                            "",
                                        )
                                        if (
                                            attend_update.status
                                            == attend_status_values[
                                                ATTEND_STATUS_NOT_STARTED
                                            ]
                                        ):
                                            yield make_script_dto(
                                                "next_chapter",
                                                attend_update.__json__(),
                                                "",
                                            )
                                            next_chapter_no = attend_update.lesson_no
                                elif isinstance(attend_update, ScriptDTO):
                                    yield make_script_dto_to_stream(attend_update)
                except BreakException:
                    if script_info:
                        yield make_script_dto("text_end", "", None)
                        script_dtos = handle_ui(
                            app,
                            user_info,
                            attend,
                            script_info,
                            input,
                            trace,
                            trace_args,
                        )
                        for script_dto in script_dtos:
                            yield make_script_dto_to_stream(script_dto)
                    db.session.commit()
                    return
            else:
                res = None
                with db.session.begin_nested():
                    res = update_lesson_status(app, attend.attend_id)
                    db.session.commit()
                
                if res and len(res) > 0:
                    for attend_update in res:
                        if isinstance(attend_update, AILessonAttendDTO):
                            if len(attend_update.lesson_no) > 2:
                                yield make_script_dto(
                                    "lesson_update", attend_update.__json__(), ""
                                )
                                if (
                                    next_chapter_no
                                    and attend_update.lesson_no.startswith(
                                        next_chapter_no
                                    )
                                ):
                                    auto_next_lesson_id = attend_update.lesson_id
                            else:
                                yield make_script_dto(
                                    "chapter_update", attend_update.__json__(), ""
                                )
                                if (
                                    attend_update.status
                                    == attend_status_values[ATTEND_STATUS_NOT_STARTED]
                                ):
                                    yield make_script_dto(
                                        "next_chapter", attend_update.__json__(), ""
                                    )
                                    next_chapter_no = attend_update.lesson_no
                        elif isinstance(attend_update, ScriptDTO):
                            yield make_script_dto_to_stream(attend_update)
            
            db.session.commit()
            
            if auto_next_lesson_id:
                pass
                # yield from run_script_inner(
                #     app,
                #     user_id,
                #     course_id,
                #     auto_next_lesson_id,
                #     input_type=INPUT_TYPE_START,
                # )
        except GeneratorExit:
            db.session.rollback()
            app.logger.info("GeneratorExit")


def run_script(
    app: Flask,
    user_id: str,
    course_id: str,
    lesson_id: str = None,
    input: str = None,
    input_type: str = None,
    script_id: str = None,
    log_id: str = None,
) -> Generator[ScriptDTO, None, None]:
    timeout = 30
    blocking_timeout = 3  # 增加阻塞超时时间，提高并发能力
    lock_key = app.config.get("REDIS_KEY_PRRFIX") + ":run_script:" + user_id
    
    lock = redis_client.lock(
        lock_key, timeout=timeout, blocking_timeout=blocking_timeout
    )
    
    session_committed = False
    
    try:
        if lock.acquire(blocking=True):
            try:
                app.logger.info(f"Lock acquired for user {user_id}")
                
                script_generator = run_script_inner(
                    app, user_id, course_id, lesson_id, input, input_type, script_id, log_id
                )
                
                for chunk in script_generator:
                    yield chunk
                    
                    if not session_committed and chunk.startswith('data: {"type":"teacher_avator"'):
                        app.logger.info(f"Initial DB operations completed for user {user_id}, releasing lock")
                        lock.release()
                        session_committed = True
                
            except Exception as e:
                app.logger.error("run_script error")
                # 输出详细的错误信息
                app.logger.error(e)
                # 输出异常信息
                error_info = {
                    "name": type(e).__name__,
                    "description": str(e),
                    "traceback": traceback.format_exc(),
                }

                if isinstance(e, AppException):
                    app.logger.info(error_info)
                    yield make_script_dto("text", str(e), None)
                else:
                    app.logger.error(error_info)
                    yield make_script_dto("text", _("COMMON.UNKNOWN_ERROR"), None)
                yield make_script_dto("text_end", "", None)
            finally:
                if lock.owned():
                    app.logger.info(f"Releasing lock for user {user_id} in finally block")
                    lock.release()
            return
        else:
            app.logger.info(f"Failed to acquire lock for user {user_id}")
            yield make_script_dto("text", "系统繁忙，请稍后再试", None)
            yield make_script_dto("text_end", "", None)
        return
    except Exception as e:
        app.logger.error(f"Unexpected error in run_script: {str(e)}")
        app.logger.error(traceback.format_exc())
        if 'lock' in locals() and lock.owned():
            lock.release()
        yield make_script_dto("text", "系统发生错误，请稍后再试", None)
        yield make_script_dto("text_end", "", None)
    return
