import traceback
from typing import Generator
from flask import Flask

from flaskr.service.common.models import AppException, raise_error
from flaskr.service.user.models import User
from flaskr.i18n import _
from ...api.langfuse import langfuse_client as langfuse
from ...service.lesson.const import (
    LESSON_TYPE_TRIAL,
    STATUS_PUBLISH,
    STATUS_DRAFT,
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
    get_script_by_id,
)
from .input_funcs import BreakException
from .output_funcs import handle_output
from .plugin import handle_input, handle_ui, check_continue
from .utils import make_script_dto_to_stream
from flaskr.service.study.dtos import AILessonAttendDTO


def handle_reload_script(
    app: Flask,
    user_id: str,
    course_id: str,
    lesson_id: str,
    script_id: str,
    input: str = None,
    input_type: str = None,
) -> Generator[str, None, None]:
    """
    Handle script execution in preview mode
    """
    ai_course_status = [STATUS_DRAFT, STATUS_PUBLISH]
    script_info = get_script_by_id(app, script_id, True)
    if not script_info:
        return

    lesson_info = AILesson.query.filter(
        AILesson.lesson_id == lesson_id,
        AILesson.status.in_(ai_course_status),
    ).first()
    if not lesson_info:
        raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")

    course_info = AICourse.query.filter(
        AICourse.course_id == course_id,
        AICourse.status.in_(ai_course_status),
    ).first()
    if not course_info:
        raise_error("LESSON.COURSE_NOT_FOUND")

    yield make_script_dto("teacher_avatar", course_info.course_teacher_avatar, "")

    # Create a temporary attend record
    attend = AICourseLessonAttendDTO(
        None,  # attend_id
        lesson_id,
        course_id,
        user_id,
        ATTEND_STATUS_IN_PROGRESS,
        1,  # script_index
    )

    # Initialize trace
    trace_args = {}
    trace_args["user_id"] = user_id
    trace_args["session_id"] = attend.attend_id
    trace_args["input"] = input
    trace_args["name"] = course_info.course_name
    trace = langfuse.trace(**trace_args)
    trace_args["output"] = ""

    user_info = User.query.filter(User.user_id == user_id).first()

    # Process user input
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

    # Handle script output
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

    # Check whether it is necessary to continue
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
        return

    # Handle UI
    if not check_script_is_last_script(app, script_info, lesson_info, True):
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
        res = update_lesson_status(app, attend.attend_id, True)
        if res:
            for attend_update in res:
                if isinstance(attend_update, AILessonAttendDTO):
                    if len(attend_update.lesson_no) > 2:
                        yield make_script_dto(
                            "lesson_update",
                            attend_update.__json__(),
                            "",
                        )
                    else:
                        yield make_script_dto(
                            "chapter_update",
                            attend_update.__json__(),
                            "",
                        )
                elif isinstance(attend_update, ScriptDTO):
                    yield make_script_dto_to_stream(attend_update)


def run_script_inner(
    app: Flask,
    user_id: str,
    course_id: str,
    lesson_id: str = None,
    input: str = None,
    input_type: str = None,
    script_id: str = None,
    log_id: str = None,
    preview_mode: bool = False,
    reload_script_id: str = None,
) -> Generator[str, None, None]:
    """
    Core function for running course scripts
    """
    with app.app_context():
        ai_course_status = [STATUS_PUBLISH]
        if preview_mode:
            ai_course_status = [STATUS_DRAFT, STATUS_PUBLISH]

        script_info = None
        try:
            attend_status_values = get_attend_status_values()
            user_info = User.query.filter(User.user_id == user_id).first()

            # When reload_script_id is provided, regenerate the script content directly
            if reload_script_id and lesson_id and course_id:
                yield from handle_reload_script(
                    app,
                    user_id,
                    course_id,
                    lesson_id,
                    reload_script_id,
                    input,
                    input_type,
                )
                return

            if not lesson_id:
                app.logger.info("lesson_id is None")
                if course_id:
                    course_info = AICourse.query.filter(
                        AICourse.course_id == course_id,
                        AICourse.status.in_(ai_course_status),
                    ).first()
                else:
                    course_info = AICourse.query.filter(
                        AICourse.status.in_(ai_course_status),
                    ).first()
                    if course_info is None:
                        raise_error("LESSON.HAS_NOT_LESSON")
                if not course_info:
                    raise_error("LESSON.COURSE_NOT_FOUND")
                yield make_script_dto(
                    "teacher_avatar", course_info.course_teacher_avatar, ""
                )
                course_id = course_info.course_id
                lessons = init_trial_lesson(app, user_id, course_id)
                attend = get_current_lesson(app, lessons)
                lesson_id = attend.lesson_id
                lesson_info = AILesson.query.filter(
                    AILesson.lesson_id == lesson_id,
                ).first()
                if not lesson_info:
                    raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
            else:
                lesson_info = None
                if preview_mode:
                    subquery = (
                        db.session.query(db.func.max(AILesson.id))
                        .filter(
                            AILesson.lesson_id == lesson_id,
                        )
                        .group_by(AILesson.lesson_id)
                    )

                    lesson_info = AILesson.query.filter(
                        AILesson.id.in_(subquery),
                        AILesson.status.in_(ai_course_status),
                    ).first()
                else:
                    lesson_info = AILesson.query.filter(
                        AILesson.lesson_id == lesson_id,
                        AILesson.status.in_(ai_course_status),
                    ).first()
                if not lesson_info:
                    raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
                course_id = lesson_info.course_id
                app.logger.info(
                    "user_id:{},course_id:{},lesson_id:{},lesson_no:{}".format(
                        user_id, course_id, lesson_id, lesson_info.lesson_no
                    )
                )
                if not lesson_info:
                    raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
                course_info = (
                    AICourse.query.filter(
                        AICourse.course_id == course_id,
                        AICourse.status.in_(ai_course_status),
                    )
                    .order_by(AICourse.id.desc())
                    .first()
                )
                if not course_info:
                    raise_error("LESSON.COURSE_NOT_FOUND")
                # return the teacher avatar
                yield make_script_dto(
                    "teacher_avatar", course_info.course_teacher_avatar, ""
                )

                attend_info = AICourseLessonAttend.query.filter(
                    AICourseLessonAttend.user_id == user_id,
                    AICourseLessonAttend.course_id == course_id,
                    AICourseLessonAttend.lesson_id == lesson_id,
                    AICourseLessonAttend.status != ATTEND_STATUS_RESET,
                ).first()
                if not attend_info:
                    if lesson_info.lesson_type == LESSON_TYPE_TRIAL:
                        app.logger.info(
                            "init trial lesson for user:{} course:{}".format(
                                user_id, course_id
                            )
                        )
                        new_attend_infos = init_trial_lesson_inner(
                            app, user_id, course_id
                        )
                        new_attend_maps = {i.lesson_id: i for i in new_attend_infos}
                        attend_info = new_attend_maps.get(lesson_id, None)
                        if not attend_info:
                            raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
                    else:
                        raise_error("COURSE.COURSE_NOT_PURCHASED")

                if (
                    attend_info.status == ATTEND_STATUS_COMPLETED
                    or attend_info.status == ATTEND_STATUS_LOCKED
                ):

                    parent_no = lesson_info.lesson_no
                    if len(parent_no) >= 2:
                        parent_no = parent_no[:-2]
                    lessons = AILesson.query.filter(
                        AILesson.lesson_no.like(parent_no + "__"),
                        AILesson.course_id == course_id,
                        AILesson.status.in_(ai_course_status),
                    ).all()
                    app.logger.info(
                        "study lesson no :{}".format(
                            ",".join([lesson.lesson_no for lesson in lessons])
                        )
                    )
                    lesson_ids = [lesson.lesson_id for lesson in lessons]
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
                db.session.flush()
            # Langfuse
            trace_args = {}
            trace_args["user_id"] = user_id
            trace_args["session_id"] = attend.attend_id
            trace_args["input"] = input
            trace_args["name"] = course_info.course_name
            trace = langfuse.trace(**trace_args)
            trace_args["output"] = ""
            next = 0
            is_first_add = False
            # get the script info and the attend updates
            script_info, attend_updates, is_first_add = get_script(
                app, attend_id=attend.attend_id, next=next, preview_mode=preview_mode
            )
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
                    # handle user input
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
                    # check if the script is start or continue
                    if input_type == INPUT_TYPE_START:
                        next = 0
                    else:
                        next = 1
                    while True and input_type != INPUT_TYPE_ASK:
                        if is_first_add:
                            is_first_add = False
                            next = 0
                        script_info, attend_updates, _ = get_script(
                            app,
                            attend_id=attend.attend_id,
                            next=next,
                            preview_mode=preview_mode,
                        )
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
                        app, script_info, lesson_info, preview_mode
                    ):
                        # check if the script_info is last script,and ui is button or continue button
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
                        res = update_lesson_status(app, attend.attend_id, preview_mode)
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
                res = update_lesson_status(app, attend.attend_id, preview_mode)
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
    preview_mode: bool = False,
    reload_script_id: str = None,
) -> Generator[ScriptDTO, None, None]:
    timeout = 5 * 60
    blocking_timeout = 1
    lock_key = app.config.get("REDIS_KEY_PREFIX") + ":run_script:" + user_id
    lock = redis_client.lock(
        lock_key, timeout=timeout, blocking_timeout=blocking_timeout
    )
    if lock.acquire(blocking=True):
        try:
            yield from run_script_inner(
                app,
                user_id,
                course_id,
                lesson_id,
                input,
                input_type,
                script_id,
                log_id,
                preview_mode,
                reload_script_id,
            )
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

            lock.release()
        return
    else:

        app.logger.info("lockfail")
        yield make_script_dto("text_end", "", None)
    return
