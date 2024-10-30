import traceback
from typing import Generator
from flask import Flask

from flaskr.service.common.models import AppException, raise_error
from flaskr.service.user.models import User
from flaskr.i18n import _
from ...api.langfuse import langfuse_client as langfuse
from ...service.lesson.const import (
    UI_TYPE_CHECKCODE,
    UI_TYPE_CONTINUED,
    UI_TYPE_LOGIN,
    UI_TYPE_PHONE,
    UI_TYPE_TO_PAY,
)
from ...service.lesson.models import AICourse, AILesson
from ...service.order.consts import (
    ATTEND_STATUS_BRANCH,
    ATTEND_STATUS_IN_PROGRESS,
    ATTEND_STATUS_NOT_STARTED,
    get_attend_status_values,
    BUY_STATUS_SUCCESS,
)
from ...service.order.funs import (
    AICourseLessonAttendDTO,
    init_trial_lesson,
    query_raw_buy_record,
)
from ...service.order.models import AICourseLessonAttend
from ...service.study.const import (
    INPUT_TYPE_ASK,
    INPUT_TYPE_START,
)
from ...service.study.dtos import ScriptDTO
from ...dao import db, redis_client
from .utils import (
    make_script_dto,
    get_script,
    update_attend_lesson_info,
    get_current_lesson,
)
from .input_funcs import BreakException
from .output_funcs import handle_output
from .plugin import handle_input, handle_ui


def run_script_inner(
    app: Flask,
    user_id: str,
    course_id: str,
    lesson_id: str = None,
    input: str = None,
    input_type: str = None,
    script_id: str = None,
) -> Generator[str, None, None]:
    with app.app_context():
        script_info = None
        try:
            attend_status_values = get_attend_status_values()
            user_info = User.query.filter(User.user_id == user_id).first()
            if not lesson_id:
                app.logger.info("lesson_id is None")
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
                yield make_script_dto(
                    "teacher_avator", course_info.course_teacher_avator, ""
                )
                course_id = course_info.course_id
                lessons = init_trial_lesson(app, user_id, course_id)
                attend = get_current_lesson(app, lessons)
                app.logger.info("{}".format(attend))
                lesson_id = attend.lesson_id
            else:
                lesson_info = AILesson.query.filter(
                    AILesson.lesson_id == lesson_id,
                    AILesson.status == 1,
                ).first()
                if not lesson_info:
                    raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
                course_id = lesson_info.course_id
                app.logger.info(
                    "user_id:{},course_id:{},lesson_id:{}".format(
                        user_id, course_id, lesson_id
                    )
                )
                if not lesson_info:
                    raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
                course_info = AICourse.query.filter(
                    AICourse.course_id == course_id,
                    AICourse.status == 1,
                ).first()
                if not course_info:
                    raise_error("LESSON.COURSE_NOT_FOUND")
                yield make_script_dto(
                    "teacher_avator", course_info.course_teacher_avator, ""
                )
                parent_no = lesson_info.lesson_no
                if len(parent_no) >= 2:
                    parent_no = parent_no[:-2]
                lessons = AILesson.query.filter(
                    AILesson.lesson_no.like(parent_no + "__"),
                    AILesson.status == 1,
                    AILesson.course_id == course_id,
                ).all()
                app.logger.info(
                    "study lesson no :{}".format(
                        ",".join([lesson.lesson_no for lesson in lessons])
                    )
                )
                lesson_ids = [lesson.lesson_id for lesson in lessons]
                attend_info = AICourseLessonAttend.query.filter(
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
                ).first()

                if not attend_info:
                    init_trial_lesson(app, user_id, course_id)
                    app.logger.info("found no attend_info")
                    lessons.sort(key=lambda x: x.lesson_no)
                    lesson_id = lessons[-1].lesson_id
                    attend_info = AICourseLessonAttend.query.filter(
                        AICourseLessonAttend.user_id == user_id,
                        AICourseLessonAttend.course_id == course_id,
                        AICourseLessonAttend.lesson_id == lesson_id,
                    ).first()

                    attends = update_attend_lesson_info(app, attend_info.attend_id)
                    for attend_update in attends:
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
                                == attend_status_values[ATTEND_STATUS_NOT_STARTED]
                            ):
                                yield make_script_dto(
                                    "next_chapter", attend_update.__json__(), ""
                                )
                lesson_id = attend_info.lesson_id
                attend = AICourseLessonAttendDTO(
                    attend_info.attend_id,
                    attend_info.lesson_id,
                    attend_info.course_id,
                    attend_info.user_id,
                    attend_info.status,
                    attend_info.script_index,
                )
                db.session.flush()
            # Langfuse 集成
            trace_args = {}
            trace_args["user_id"] = user_id
            trace_args["session_id"] = attend.attend_id
            trace_args["input"] = input
            trace_args["name"] = "ai-python"
            trace = langfuse.trace(**trace_args)

            trace_args["output"] = ""
            next = 0
            is_first_add = False
            # 如果有用户输入,就得到当前这一条,否则得到下一条
            script_info, attend_updates, is_first_add = get_script(
                app, attend_id=attend.attend_id, next=next
            )
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
                            == attend_status_values[ATTEND_STATUS_NOT_STARTED]
                        ):
                            yield make_script_dto(
                                "next_chapter", attend_update.__json__(), ""
                            )
            if script_info:
                try:
                    check_paid = True
                    # to do  seperate
                    if script_info.script_ui_type == UI_TYPE_TO_PAY:
                        order = query_raw_buy_record(app, user_id, course_id)
                        if order and order.status == BUY_STATUS_SUCCESS:
                            # 如果已经购买
                            check_paid = True
                        else:
                            check_paid = False

                    else:
                        # 处理用户输入
                        response = handle_input(
                            app,
                            user_id,
                            input_type,
                            attend,
                            script_info,
                            input,
                            trace,
                            trace_args,
                        )
                        if response:
                            yield from response

                    # 如果是Start或是Continue，就不需要再次获取脚本
                    if input_type == INPUT_TYPE_START:
                        next = 0
                    else:
                        next = check_paid and 1 or 0
                    while True and input_type != INPUT_TYPE_ASK:
                        app.logger.info(
                            "next:{} is_first:{}".format(next, is_first_add)
                        )
                        if is_first_add:
                            is_first_add = False
                            next = 0
                        script_info, attend_updates, _ = get_script(
                            app, attend_id=attend.attend_id, next=next
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
                            if (
                                script_info.script_ui_type
                                in [UI_TYPE_PHONE, UI_TYPE_CHECKCODE, UI_TYPE_LOGIN]
                            ) and user_info.user_state != 0:
                                next = 1
                                continue
                            response = handle_output(
                                app,
                                user_id,
                                attend,
                                script_info,
                                input,
                                trace,
                                trace_args,
                            )
                            if response:
                                yield from response

                            app.logger.info(
                                "script ui type {}".format(script_info.script_ui_type)
                            )
                            if script_info.script_ui_type == UI_TYPE_CONTINUED:
                                continue
                            if (
                                script_info.script_ui_type == UI_TYPE_PHONE
                                and user_info.user_state != 0
                            ):
                                continue
                            if (
                                script_info.script_ui_type == UI_TYPE_CHECKCODE
                                and user_info.user_state != 0
                            ):
                                continue
                            if (
                                script_info.script_ui_type == UI_TYPE_LOGIN
                                and user_info.user_state != 0
                            ):
                                continue

                            break
                        else:
                            break
                    if script_info:
                        # 返回下一轮交互
                        # 返回  下一轮的交互方式
                        if script_info.script_ui_type == UI_TYPE_CONTINUED:
                            next = 1
                            input_type = None
                        else:
                            yield from handle_ui(
                                app,
                                user_id,
                                attend,
                                script_info,
                                input,
                                trace,
                                trace_args,
                            )
                    else:
                        attends = update_attend_lesson_info(app, attend.attend_id)
                        for attend_update in attends:
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
                                    == attend_status_values[ATTEND_STATUS_NOT_STARTED]
                                ):
                                    yield make_script_dto(
                                        "next_chapter", attend_update.__json__(), ""
                                    )
                        app.logger.info("script_info is None")
                except BreakException:
                    if script_info:
                        yield make_script_dto("text_end", "", None)
                        yield from handle_ui(
                            app,
                            user_id,
                            attend,
                            script_info,
                            input,
                            trace,
                            trace_args,
                        )
                    db.session.commit()
                    return
            else:
                app.logger.info("script_info is None,to update attend")
                attends = update_attend_lesson_info(app, attend.attend_id)
                for attend_update in attends:
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
                            == attend_status_values[ATTEND_STATUS_NOT_STARTED]
                        ):
                            yield make_script_dto(
                                "next_chapter", attend_update.__json__(), ""
                            )
            db.session.commit()
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
) -> Generator[ScriptDTO, None, None]:
    timeout = 5 * 60
    blocking_timeout = 1
    lock_key = app.config.get("REDIS_KEY_PRRFIX") + ":run_script:" + user_id
    lock = redis_client.lock(
        lock_key, timeout=timeout, blocking_timeout=blocking_timeout
    )
    if lock.acquire(blocking=True):
        try:
            app.logger.info("run_script with lock")
            yield from run_script_inner(
                app, user_id, course_id, lesson_id, input, input_type, script_id
            )
            app.logger.info("run_script end")
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
            app.logger.error(error_info)
            if isinstance(e, AppException):
                yield make_script_dto("text", str(e), None)
            else:
                yield make_script_dto("text", _("COMMON.UNKNOWN_ERROR"), None)
            yield make_script_dto("text_end", "", None)
        finally:

            lock.release()
            app.logger.info("run_script release lock")
        return
    else:

        app.logger.info("lockfail")
        yield make_script_dto("text_end", "", None)
    return
