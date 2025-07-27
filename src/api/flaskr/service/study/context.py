from flask import Flask
from flaskr.dao import db
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto, ShifuInfoDto
from flaskr.service.study.utils import make_script_dto
from flaskr.service.shifu.models import (
    ShifuDraftBlock,
    ShifuPublishedBlock,
    ShifuDraftOutlineItem,
    ShifuPublishedOutlineItem,
)
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.adapter import generate_block_dto_from_model_internal
from typing import Generator, Union
from langfuse.client import StatefulTraceClient
from ...api.langfuse import langfuse_client as langfuse, MockClient
from flaskr.service.common import raise_error
from flaskr.service.order.consts import ATTEND_STATUS_RESET, ATTEND_STATUS_IN_PROGRESS
from flaskr.service.lesson.const import LESSON_TYPE_NORMAL
from flaskr.service.study.plugin import (
    handle_shifu_input,
    handle_shifu_output,
)
import queue
from enum import Enum
from flaskr.service.user.models import User


def get_can_continue(attend_id: str) -> bool:
    attend_info = AICourseLessonAttend.query.filter(
        AICourseLessonAttend.attend_id == attend_id,
    ).first()
    return attend_info.status != ATTEND_STATUS_RESET


class RunType(Enum):
    INPUT = "input"
    OUTPUT = "output"


class RunScriptContext:
    user_id: str
    attend_id: str
    is_paid: bool
    preview_mode: bool
    _q: queue.Queue
    _outline_item_info: ShifuOutlineItemDto
    _struct: HistoryItem
    _user_info: User
    _is_paid: bool
    _preview_mode: bool
    _shifu_ids: list[str]
    _run_type: RunType
    _app: Flask
    _outline_model: Union[ShifuDraftOutlineItem, ShifuPublishedOutlineItem]
    _block_model: Union[ShifuDraftBlock, ShifuPublishedBlock]
    _trace_args: dict
    _shifu_info: ShifuInfoDto
    _trace: Union[StatefulTraceClient, MockClient]
    _input_type: str
    _input: str
    _can_continue: bool

    def __init__(
        self,
        app: Flask,
        shifu_info: ShifuInfoDto,
        struct: HistoryItem,
        outline_item_info: ShifuOutlineItemDto,
        user_info: User,
        is_paid: bool,
        preview_mode: bool,
    ):
        self.app = app
        self._struct = struct
        self._outline_item_info = outline_item_info
        self._user_info = user_info
        self._is_paid = is_paid
        self._preview_mode = preview_mode
        self._shifu_info = shifu_info

        self.shifu_ids = []
        self.outline_item_ids = []
        self.current_outline_item = None
        self._run_type = RunType.INPUT
        self._can_continue = True

        if preview_mode:
            self._outline_model = ShifuDraftOutlineItem
            self._block_model = ShifuDraftBlock
        else:
            self._outline_model = ShifuPublishedOutlineItem
            self._block_model = ShifuPublishedBlock

        # get current attend
        self._q = queue.Queue()
        self._q.put(struct)
        while not self._q.empty():
            item = self._q.get()
            if item.bid == outline_item_info.bid:
                self._current_outline_item = item
                break
            if item.children:
                for child in item.children:
                    self._q.put(child)
        self._current_attend = self._get_current_attend()
        self.app.logger.info(
            f"current_attend: {self._current_attend.attend_id} {self._current_attend.script_index}"
        )

        self._trace_args = {}
        self._trace_args["user_id"] = user_info.user_id
        self._trace_args["session_id"] = self._current_attend.attend_id
        self._trace_args["input"] = ""
        self._trace_args["name"] = self._outline_item_info.title
        self._trace = langfuse.trace(**self._trace_args)
        self._trace_args["output"] = ""

    def _get_current_attend(self) -> AICourseLessonAttend:
        attend_info: AICourseLessonAttend = (
            AICourseLessonAttend.query.filter(
                AICourseLessonAttend.lesson_id == self._outline_item_info.bid,
                AICourseLessonAttend.user_id == self._user_info.user_id,
                AICourseLessonAttend.status != ATTEND_STATUS_RESET,
            )
            .order_by(AICourseLessonAttend.id.desc())
            .first()
        )
        if not attend_info:
            outline_item_info: Union[
                ShifuDraftOutlineItem, ShifuPublishedOutlineItem
            ] = self._outline_model.query.filter(
                self._outline_model.id == self._outline_item_info.id,
            ).first()
            if not outline_item_info:
                raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
            if outline_item_info.type == LESSON_TYPE_NORMAL:
                if (not self._is_paid) and (not self._preview_mode):
                    raise_error("ORDER.COURSE_NOT_PAID")
            attend_info = AICourseLessonAttend()
            attend_info.lesson_id = outline_item_info.outline_item_bid
            attend_info.course_id = outline_item_info.shifu_bid
            attend_info.user_id = self._user_id
            attend_info.status = ATTEND_STATUS_IN_PROGRESS
            attend_info.script_index = 0
            db.session.add(attend_info)
            db.session.flush()
        return attend_info

    def _get_current_outline_item(self) -> ShifuOutlineItemDto:
        return self._current_outline_item

    def set_input(self, input: str, input_type: str):
        self._trace_args["input"] = input
        self._trace_args["input_type"] = input_type
        self._input_type = input_type
        self._input = input

    def run(self, app: Flask) -> Generator[str, None, None]:
        app.logger.info(
            f"run_context.run {self._current_attend.script_index} {self._current_attend.status}"
        )
        yield make_script_dto("teacher_avatar", self._shifu_info.avatar, "")
        if not self._current_attend:
            self._current_attend = self._get_current_attend()

        if self._current_attend.script_index >= len(
            self._current_outline_item.children
        ):
            app.logger.info(
                f"no more script for {self._current_outline_item} ,to get next outline item"
            )

        block_id = self._current_outline_item.children[
            self._current_attend.script_index
        ].id

        block_info: Union[ShifuDraftBlock, ShifuPublishedBlock] = (
            self._block_model.query.filter(
                self._block_model.id == block_id,
            ).first()
        )
        if not block_info:
            raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")

        block_dto = generate_block_dto_from_model_internal(block_info)
        # if check_continue_shifu(app,
        #                         self._user_info,
        #                         self._current_attend.attend_id,
        #                         self._outline_item_info,
        #                         block_dto,
        #                         self._trace_args,
        #                         self._trace):
        #     self._can_continue = True
        #     self._current_attend.script_index += 1
        #     self._current_attend.status = ATTEND_STATUS_IN_PROGRESS
        #     self._input_type = "continue"
        #     self.app.logger.info(f"block type: {block_dto.type} continue")
        #     self.app.logger.info(f"line 194")
        #     db.session.flush()
        #     self.app.logger.info(f"block type: {block_dto.type} continue,has_next: {self._can_continue} and return.")
        #     # here will be invoke 'run' on top of this function
        #     return

        app.logger.info(f"block type: {block_dto.type} {self._input_type}")
        if self._run_type == RunType.INPUT:
            res = handle_shifu_input(
                app=app,
                user_info=self._user_info,
                attend_id=self._current_attend.attend_id,
                outline_item_info=self._outline_item_info,
                block_dto=block_dto,
                trace_args=self._trace_args,
                trace=self._trace,
            )
            if res:
                yield from res
            self._can_continue = True
            self._current_attend.script_index += 1
            self._current_attend.status = ATTEND_STATUS_IN_PROGRESS
            self._input_type = "continue"
            self._run_type = RunType.OUTPUT
            db.session.flush()

        else:
            res = handle_shifu_output(
                app=app,
                user_info=self._user_info,
                attend_id=self._current_attend.attend_id,
                outline_item_info=self._outline_item_info,
                block_dto=block_dto,
                trace_args=self._trace_args,
                trace=self._trace,
            )
            if res:
                yield from res
                self._can_continue = True
                self._current_attend.script_index += 1
                self._current_attend.status = ATTEND_STATUS_IN_PROGRESS
                self._input_type = "continue"
                self._run_type = RunType.OUTPUT
                db.session.flush()
                return

        self._trace_args["output"] = block_info.content
        self._trace.update(**self._trace_args)

        # self._trace_args["output"] = block_info.content

        # self._run_type = RunType.OUTPUT

    def has_next(self) -> bool:
        self.app.logger.info(f"has_next {self._can_continue}")
        return self._can_continue
