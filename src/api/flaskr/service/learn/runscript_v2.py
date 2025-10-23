import traceback
import threading
import queue
import contextlib
from typing import Generator
from flask import Flask

from flaskr.service.common.models import AppException, raise_error
from flaskr.service.user.models import User
from flaskr.i18n import _
import json


from flaskr.service.learn.learn_dtos import RunMarkdownFlowDTO, RunStatusDTO
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
    stop_event: threading.Event | None = None,
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
                if stop_event and stop_event.is_set():
                    app.logger.info("run_script_inner cancelled before reload")
                    db.session.rollback()
                    return
                yield from run_script_context.reload(app, reload_generated_block_bid)
                db.session.commit()
            while run_script_context.has_next():
                if stop_event and stop_event.is_set():
                    app.logger.info("run_script_inner cancelled by stop_event")
                    db.session.rollback()
                    return
                app.logger.info("run_script_context.run")
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
    heartbeat_interval = float(app.config.get("SSE_HEARTBEAT_INTERVAL", 0.1))
    lock_key = (
        app.config.get("REDIS_KEY_PREFIX")
        + ":run_script:"
        + user_bid
        + ":"
        + outline_bid
    )
    lock = redis_client.lock(
        lock_key, timeout=timeout, blocking_timeout=blocking_timeout
    )
    if lock.acquire(blocking=True):
        stop_event = threading.Event()
        output_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        res = run_script_inner(
            app=app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            input=input,
            input_type=input_type,
            reload_generated_block_bid=reload_generated_block_bid,
            preview_mode=preview_mode,
            stop_event=stop_event,
        )

        def producer():
            try:
                for item in res:
                    if stop_event.is_set():
                        break
                    output_queue.put(("data", item))
            except Exception as exc:
                if stop_event.is_set():
                    app.logger.info(
                        "run_script producer stopped due to client disconnect: %s",
                        type(exc).__name__,
                    )
                    return
                output_queue.put(("error", exc))
            finally:
                with contextlib.suppress(Exception):
                    res.close()
                output_queue.put(("done", None))

        producer_thread = threading.Thread(
            target=producer, name="run_script_stream_producer", daemon=True
        )
        producer_thread.start()

        stream_error: Exception | None = None
        client_disconnected = False
        done_received = False
        try:
            while True:
                try:
                    kind, payload = output_queue.get(timeout=heartbeat_interval)
                except queue.Empty:
                    if done_received or client_disconnected:
                        break
                    try:
                        yield (
                            "data: "
                            + json.dumps(
                                {"type": "heartbeat"}, default=fmt, ensure_ascii=False
                            )
                            + "\n\n".encode("utf-8").decode("utf-8")
                        )
                    except GeneratorExit:
                        client_disconnected = True
                        stop_event.set()
                        app.logger.info(
                            "Client disconnected from SSE stream during heartbeat"
                        )
                        break
                    except (ConnectionError, BrokenPipeError, OSError) as exc:
                        client_disconnected = True
                        stop_event.set()
                        app.logger.info(
                            "Client disconnected from SSE stream during heartbeat: %s",
                            repr(exc),
                        )
                        break
                    continue

                if kind == "data":
                    try:
                        yield (
                            "data: "
                            + json.dumps(payload, default=fmt, ensure_ascii=False)
                            + "\n\n".encode("utf-8").decode("utf-8")
                        )
                    except GeneratorExit:
                        client_disconnected = True
                        stop_event.set()
                        app.logger.info(
                            "Client disconnected from SSE stream (GeneratorExit)"
                        )
                        break
                    except (ConnectionError, BrokenPipeError, OSError) as exc:
                        client_disconnected = True
                        stop_event.set()
                        app.logger.info(
                            "Client disconnected from SSE stream: %s", repr(exc)
                        )
                        break
                elif kind == "error":
                    if isinstance(payload, Exception):
                        stream_error = payload
                    else:
                        stream_error = Exception(str(payload))
                    break
                elif kind == "done":
                    done_received = True
                    break
        finally:
            stop_event.set()
            producer_thread.join(timeout=0.1)
            if producer_thread.is_alive():
                app.logger.warning("run_script producer thread did not stop in time")
            lock.release()

        if stream_error and not client_disconnected:
            if isinstance(stream_error, Exception):
                app.logger.error("run_script error")
                app.logger.error(stream_error)
                error_traceback = "".join(
                    traceback.format_exception(
                        type(stream_error),
                        stream_error,
                        stream_error.__traceback__,
                    )
                )
                error_info = {
                    "name": type(stream_error).__name__,
                    "description": str(stream_error),
                    "traceback": error_traceback,
                }

                if isinstance(stream_error, AppException):
                    app.logger.info(error_info)
                    yield (
                        "data: "
                        + json.dumps(
                            RunMarkdownFlowDTO(
                                outline_bid=outline_bid,
                                generated_block_bid="",
                                type=GeneratedType.CONTENT,
                                content=str(stream_error),
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
                            content="",
                        ),
                        default=fmt,
                        ensure_ascii=False,
                    )
                    + "\n\n".encode("utf-8").decode("utf-8")
                )
        return
    else:
        app.logger.warning("lockfail")
        yield make_script_dto("text_end", "", None)
    return


def get_run_status(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
) -> RunStatusDTO:
    lock_key = (
        app.config.get("REDIS_KEY_PREFIX")
        + ":run_script:"
        + user_bid
        + ":"
        + outline_bid
    )
    lock = redis_client.lock(lock_key, timeout=300, blocking_timeout=0)
    if lock.acquire(blocking=False):
        # Lock acquired successfully, so no other process is running
        lock.release()
        return RunStatusDTO(is_running=False, running_time=0)
    else:
        # Lock is held by another process
        # We can't get the exact running time without additional metadata
        return RunStatusDTO(is_running=True, running_time=0)
