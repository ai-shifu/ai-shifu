import traceback
from typing import Generator
from flask import Flask

from flaskr.service.common.models import AppException, raise_error
from flaskr.service.user.models import User
from flaskr.i18n import _
import json


from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO
from flaskr.dao import db, redis_client
from flaskr.service.learn.utils import (
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
from flaskr.service.order.models import Order
from flaskr.service.order.consts import ORDER_STATUS_SUCCESS
from flaskr.service.learn.context_v2 import RunScriptContextV2
from flaskr.service.learn.input_funcs import BreakException
from flaskr.service.learn.learn_dtos import GeneratedType
import datetime


def run_script_inner(
    app: Flask,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    input: str | dict = None,
    input_type: str = None,
    reload_generated_block_bid: str = None,
    preview_mode: bool = False,
) -> Generator[RunMarkdownFlowDTO, None, None]:
    """
    Core function for running course scripts
    """
    with app.app_context():
        try:
            user_info = User.query.filter(User.user_id == user_bid).first()
            shifu_info: ShifuInfoDto = None
            outline_item_info: ShifuOutlineItemDto = None
            struct_info: HistoryItem = None
            if not outline_bid:
                app.logger.info("lesson_id is None")
                if not shifu_bid:
                    shifu_info = get_default_shifu_dto(app, preview_mode)
                else:
                    shifu_info = get_shifu_dto(app, shifu_bid, preview_mode)
                if not shifu_info:
                    raise_error("LESSON.HAS_NOT_LESSON")
                shifu_bid = shifu_info.bid
            else:
                outline_item_info = get_outline_item_dto(app, outline_bid, preview_mode)
                if not outline_item_info:
                    raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
                shifu_bid = outline_item_info.shifu_bid
                shifu_info = get_shifu_dto(app, shifu_bid, preview_mode)
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
                    Order.query.filter(
                        Order.user_bid == user_bid,
                        Order.shifu_bid == shifu_bid,
                        Order.status == ORDER_STATUS_SUCCESS,
                        Order.deleted == 0,
                    )
                    .order_by(Order.id.desc())
                    .first()
                )
                if not success_buy_record:
                    is_paid = False
                else:
                    is_paid = True
            else:
                is_paid = True

            run_script_context: RunScriptContextV2 = RunScriptContextV2(
                app=app,
                shifu_info=shifu_info,
                struct=struct_info,
                outline_item_info=outline_item_info,
                user_info=user_info,
                is_paid=is_paid,
                preview_mode=preview_mode,
            )

            run_script_context.set_input(input, input_type)
            if reload_generated_block_bid:
                yield from run_script_context.reload(app, reload_generated_block_bid)
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


def fmt(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    else:
        return o.__json__()


def run_script(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    input: str | dict = None,
    input_type: str = None,
    reload_generated_block_bid: str = None,
    preview_mode: bool = False,
) -> Generator[str, None, None]:
    timeout = 5 * 60
    blocking_timeout = 1
    lock_key = app.config.get("REDIS_KEY_PREFIX") + ":run_script:" + user_bid
    lock = redis_client.lock(
        lock_key, timeout=timeout, blocking_timeout=blocking_timeout
    )
    if lock.acquire(blocking=True):
        try:
            res = run_script_inner(
                app=app,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
                input=input,
                input_type=input_type,
                reload_generated_block_bid=reload_generated_block_bid,
                preview_mode=preview_mode,
            )
            for item in res:
                yield (
                    "data: "
                    + json.dumps(item, default=fmt, ensure_ascii=False)
                    + "\n\n".encode("utf-8").decode("utf-8")
                )
        except Exception as e:
            app.logger.error("run_script error")
            app.logger.error(e)
            error_info = {
                "name": type(e).__name__,
                "description": str(e),
                "traceback": traceback.format_exc(),
            }

            if isinstance(e, AppException):
                app.logger.info(error_info)
                yield (
                    "data: "
                    + json.dumps(
                        RunMarkdownFlowDTO(
                            outline_bid=outline_bid,
                            generated_block_bid="",
                            type=GeneratedType.CONTENT,
                            content=str(e),
                        ),
                        default=fmt,
                        ensure_ascii=False,
                    )
                    + "\n\n".encode("utf-8").decode("utf-8")
                )
            else:
                app.logger.error(error_info)
                yield (
                    "data: "
                    + json.dumps(
                        RunMarkdownFlowDTO(
                            outline_bid=outline_bid,
                            generated_block_bid="",
                            type=GeneratedType.CONTENT,
                            content=str(_("COMMON.UNKNOWN_ERROR")),
                        ),
                        default=fmt,
                        ensure_ascii=False,
                    )
                    + "\n\n".encode("utf-8").decode("utf-8")
                )
            yield (
                "data: "
                + json.dumps(
                    RunMarkdownFlowDTO(
                        outline_bid=outline_bid,
                        generated_block_bid="",
                        type=GeneratedType.BREAK,
                        content=None,
                    ),
                    default=fmt,
                    ensure_ascii=False,
                )
                + "\n\n".encode("utf-8").decode("utf-8")
            )
        finally:
            lock.release()
        return
    else:
        app.logger.warning("lockfail")
        yield make_script_dto("text_end", "", None)
    return
