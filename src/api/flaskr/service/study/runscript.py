import traceback
from typing import Generator
from flask import Flask

from flaskr.service.common.models import AppException, raise_error
from flaskr.service.user.models import User
from flaskr.i18n import _


from ...service.study.dtos import ScriptDTO
from ...dao import db, redis_client
from .utils import (
    make_script_dto,
)
from flaskr.service.shifu.shifu_struct_manager import (
    get_shifu_dto,
    get_outline_item_dto,
    ShifuInfoDto,
    ShifuOutlineItemDto,
    get_default_shifu_dto,
    get_shifu_struct,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.order.models import AICourseBuyRecord
from flaskr.service.order.consts import BUY_STATUS_SUCCESS
from flaskr.service.study.context import RunScriptContext
from flaskr.service.study.input_funcs import BreakException


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
        # script_info = None
        try:
            user_info = User.query.filter(User.user_id == user_id).first()
            shifu_info: ShifuInfoDto = None
            outline_item_info: ShifuOutlineItemDto = None
            struct_info: HistoryItem = None
            if not lesson_id:
                app.logger.info("lesson_id is None")
                if not course_id:
                    shifu_info = get_default_shifu_dto(app, preview_mode)
                else:
                    shifu_info = get_shifu_dto(app, course_id, preview_mode)
                if not shifu_info:
                    raise_error("LESSON.HAS_NOT_LESSON")
                course_id = shifu_info.bid
            else:
                outline_item_info = get_outline_item_dto(app, lesson_id, preview_mode)
                if not outline_item_info:
                    raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
                course_id = outline_item_info.shifu_bid
                shifu_info = get_shifu_dto(app, course_id, preview_mode)
                if not shifu_info:
                    raise_error("LESSON.COURSE_NOT_FOUND")

            struct_info = get_shifu_struct(app, shifu_info.bid, preview_mode)
            if not struct_info:
                raise_error("LESSON.SHIFU_NOT_FOUND")
            if not outline_item_info:
                lesson_info = None
            else:
                lesson_info = outline_item_info
                app.logger.info(f"lesson_info: {lesson_info.__json__()}")

            if shifu_info.price > 0:
                success_buy_record = (
                    AICourseBuyRecord.query.filter(
                        AICourseBuyRecord.user_id == user_id,
                        AICourseBuyRecord.course_id == course_id,
                        AICourseBuyRecord.status == BUY_STATUS_SUCCESS,
                    )
                    .order_by(AICourseBuyRecord.id.desc())
                    .first()
                )
                if not success_buy_record:
                    is_paid = False
                else:
                    is_paid = True
            else:
                is_paid = True

            run_script_context: RunScriptContext = RunScriptContext(
                app=app,
                shifu_info=shifu_info,
                struct=struct_info,
                outline_item_info=outline_item_info,
                user_info=user_info,
                is_paid=is_paid,
                preview_mode=preview_mode,
            )

            run_script_context.set_input(input, input_type)
            if reload_script_id:
                yield from run_script_context.reload(app, reload_script_id)
                db.session.commit()
                return
            while run_script_context.has_next():
                yield from run_script_context.run(app)
            db.session.commit()
        except BreakException:
            db.session.commit()
            app.logger.info("BreakException")
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
