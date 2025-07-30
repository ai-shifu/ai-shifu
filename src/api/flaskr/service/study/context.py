from flask import Flask
from flaskr.dao import db
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto, ShifuInfoDto
from flaskr.service.study.utils import make_script_dto
from flaskr.service.shifu.models import (
    ShifuDraftBlock,
    ShifuPublishedBlock,
    ShifuDraftOutlineItem,
    ShifuPublishedOutlineItem,
    ShifuDraftShifu,
    ShifuPublishedShifu,
)
from flaskr.service.order.models import AICourseLessonAttend
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.shifu_struct_manager import get_outline_item_dto
from flaskr.service.shifu.adapter import (
    generate_block_dto_from_model_internal,
    BlockDTO,
)
from typing import Generator, Union
from langfuse.client import StatefulTraceClient
from ...api.langfuse import langfuse_client as langfuse, MockClient
from flaskr.service.common import raise_error
from flaskr.service.order.consts import (
    ATTEND_STATUS_RESET,
    ATTEND_STATUS_IN_PROGRESS,
    ATTEND_STATUS_COMPLETED,
    ATTEND_STATUS_NOT_STARTED,
    ATTEND_STATUS_LOCKED,
)
from flaskr.service.lesson.const import LESSON_TYPE_NORMAL
from flaskr.service.study.plugin import (
    handle_block_input,
    handle_block_output,
    check_block_continue,
)
import queue
from enum import Enum
from flaskr.service.user.models import User
from flaskr.service.order.consts import get_attend_status_values
from flaskr.service.shifu.struct_uils import find_node_with_parents
import threading
from pydantic import BaseModel
from flaskr.util import generate_id
from flaskr.service.shifu.dtos import GotoDTO, GotoConditionDTO
from flaskr.service.profile.funcs import get_user_variable_by_variable_id

context_local = threading.local()


def get_can_continue(attend_id: str) -> bool:
    attend_info = AICourseLessonAttend.query.filter(
        AICourseLessonAttend.attend_id == attend_id,
    ).first()
    return attend_info.status != ATTEND_STATUS_RESET


class RunType(Enum):
    INPUT = "input"
    OUTPUT = "output"


class LLMSettings(BaseModel):
    model: str
    temperature: float

    def __str__(self):
        return f"model: {self.model}, temperature: {self.temperature}"

    def __repr__(self):
        return self.__str__()

    def __json__(self):
        return self.__str__()


# outline update type
# outline is a node when has outline item as children
# outline is a leaf when has block item as children
# outline is a leaf when has no children
class _OutlineUpateType(Enum):
    NODE_COMPLETED = "node_completed"
    NODE_START = "node_start"
    LEAF_COMPLETED = "leaf_completed"
    LEAF_START = "leaf_start"


class _OutlineUpate:
    type: _OutlineUpateType
    outline_item_info: ShifuOutlineItemDto

    def __init__(self, type: _OutlineUpateType, outline_item_info: ShifuOutlineItemDto):
        self.type = type
        self.outline_item_info = outline_item_info


class RunScriptInfo:
    attend: AICourseLessonAttend
    outline_item_info: ShifuOutlineItemDto
    block_dto: BlockDTO

    def __init__(
        self,
        attend: AICourseLessonAttend,
        outline_item_info: ShifuOutlineItemDto,
        block_dto: BlockDTO,
    ):
        self.attend = attend
        self.outline_item_info = outline_item_info
        self.block_dto = block_dto


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
    _shifu_model: Union[ShifuDraftShifu, ShifuPublishedShifu]
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
            self._shifu_model = ShifuDraftShifu
        else:
            self._outline_model = ShifuPublishedOutlineItem
            self._block_model = ShifuPublishedBlock
            self._shifu_model = ShifuPublishedShifu
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
        self._current_attend = self._get_current_attend(self._outline_item_info)
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

        context_local.current_context = self

    @staticmethod
    def get_current_context(app: Flask) -> "RunScriptContext":
        return context_local.current_context

    def _get_current_attend(
        self, outline_item_info: ShifuOutlineItemDto
    ) -> AICourseLessonAttend:
        attend_info: AICourseLessonAttend = (
            AICourseLessonAttend.query.filter(
                AICourseLessonAttend.lesson_id == outline_item_info.bid,
                AICourseLessonAttend.user_id == self._user_info.user_id,
                AICourseLessonAttend.status != ATTEND_STATUS_RESET,
            )
            .order_by(AICourseLessonAttend.id.desc())
            .first()
        )
        if not attend_info:
            outline_item_info_db: Union[
                ShifuDraftOutlineItem, ShifuPublishedOutlineItem
            ] = self._outline_model.query.filter(
                self._outline_model.id == outline_item_info.id,
            ).first()
            if not outline_item_info:
                raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
            if outline_item_info.type == LESSON_TYPE_NORMAL:
                if (not self._is_paid) and (not self._preview_mode):
                    raise_error("ORDER.COURSE_NOT_PAID")
            parent_path = find_node_with_parents(
                self._struct, outline_item_info_db.outline_item_bid
            )
            attend_info = None
            for item in parent_path:
                if item.type == "outline":
                    attend_info = AICourseLessonAttend.query.filter(
                        AICourseLessonAttend.lesson_id == item.id,
                        AICourseLessonAttend.user_id == self._user_info.user_id,
                        AICourseLessonAttend.status != ATTEND_STATUS_RESET,
                    ).first()
                    if attend_info:

                        continue
                    attend_info = AICourseLessonAttend()
                    attend_info.lesson_id = outline_item_info_db.outline_item_bid
                    attend_info.course_id = outline_item_info_db.shifu_bid
                    attend_info.user_id = self._user_info.user_id
                    attend_info.status = ATTEND_STATUS_NOT_STARTED
                    attend_info.attend_id = generate_id(self.app)
                    attend_info.script_index = 0
                    db.session.add(attend_info)
                    db.session.flush()
                    break
        return attend_info

    # outline is a leaf when has block item as children
    # outline is a node when has outline item as children
    # outline is a leaf when has no children
    def _is_leaf_outline_item(self, outline_item_info: ShifuOutlineItemDto) -> bool:
        if outline_item_info.children:
            if outline_item_info.children[0].type == "block":
                return True
            if outline_item_info.children[0].type == "outline":
                return False
        if outline_item_info.type == "outline":
            return True
        return False

    def _get_next_outline_item(self) -> list[_OutlineUpate]:
        res = []

        def _mark_sub_node_completed(
            outline_item_info: HistoryItem, res: list[_OutlineUpate]
        ):
            q = queue.Queue()
            q.put(self._struct)
            if self._is_leaf_outline_item(outline_item_info):
                res.append(
                    _OutlineUpate(_OutlineUpateType.LEAF_COMPLETED, outline_item_info)
                )
            else:
                res.append(
                    _OutlineUpate(_OutlineUpateType.NODE_COMPLETED, outline_item_info)
                )
            while not q.empty():
                item: HistoryItem = q.get()
                if item.children and outline_item_info.bid in [
                    child.bid for child in item.children
                ]:
                    index = [child.bid for child in item.children].index(
                        outline_item_info.bid
                    )
                    if index < len(item.children) - 1:
                        # not sub node
                        current_node = item.children[index + 1]
                        while (
                            current_node.children
                            and current_node.children[0].type == "outline"
                        ):
                            res.append(
                                _OutlineUpate(
                                    _OutlineUpateType.NODE_START, current_node
                                )
                            )
                            current_node = current_node.children[0]
                        res.append(
                            _OutlineUpate(_OutlineUpateType.LEAF_START, current_node)
                        )
                        return
                    elif index == len(item.children) - 1 and item.type == "outline":
                        _mark_sub_node_completed(item, res)

                if item.children and item.children[0].type == "outline":
                    for child in item.children:
                        q.put(child)

        def _mark_sub_node_start(
            outline_item_info: HistoryItem, res: list[_OutlineUpate]
        ):
            path = find_node_with_parents(self._struct, outline_item_info.bid)
            for item in path:
                if item.type == "outline":
                    if item.children and item.children[0].type == "outline":
                        res.append(_OutlineUpate(_OutlineUpateType.NODE_START, item))
                    else:
                        res.append(_OutlineUpate(_OutlineUpateType.LEAF_START, item))

        if self._current_attend.script_index >= len(
            self._current_outline_item.children
        ):
            _mark_sub_node_completed(self._current_outline_item, res)
        if self._current_attend.status == ATTEND_STATUS_NOT_STARTED:
            _mark_sub_node_start(self._current_outline_item, res)
        return res

    def _get_current_outline_item(self) -> ShifuOutlineItemDto:
        return self._current_outline_item

    def _render_outline_updates(
        self, outline_updates: list[_OutlineUpate]
    ) -> Generator[str, None, None]:
        attend_status_values = get_attend_status_values()
        shif_bids = [o.outline_item_info.bid for o in outline_updates]
        outline_item_info_db: Union[
            ShifuDraftOutlineItem, ShifuPublishedOutlineItem
        ] = self._outline_model.query.filter(
            self._outline_model.outline_item_bid.in_(shif_bids),
            self._outline_model.deleted == 0,
        ).all()
        outline_item_info_map = {o.outline_item_bid: o for o in outline_item_info_db}
        for update in outline_updates:
            self.app.logger.info(
                f"outline update: {update.type} {update.outline_item_info.bid}"
            )
            outline_item_info = outline_item_info_map.get(
                update.outline_item_info.bid, None
            )
            if outline_item_info:
                outline_item_info_args = {
                    "lesson_no": outline_item_info.position,
                    "lesson_name": outline_item_info.title,
                }
            else:
                outline_item_info_args = {}
            if update.type == _OutlineUpateType.LEAF_START:
                self._current_outline_item = update.outline_item_info
                if self._current_attend.lesson_id == update.outline_item_info.bid:
                    self._current_attend.status = ATTEND_STATUS_IN_PROGRESS
                    self._current_attend.script_index = 0
                    db.session.flush()
                    continue
                self._current_attend = self._get_current_attend(
                    self._current_outline_item
                )
                self.app.logger.info(
                    f"current_attend: {self._current_attend.lesson_id} {self._current_attend.status} {self._current_attend.script_index}"
                )

                if (
                    self._current_attend.status == ATTEND_STATUS_NOT_STARTED
                    or self._current_attend.status == ATTEND_STATUS_LOCKED
                ):
                    self._current_attend.status = ATTEND_STATUS_IN_PROGRESS
                    self._current_attend.script_index = 0
                    db.session.flush()
                    yield make_script_dto(
                        "lesson_update",
                        {
                            "lesson_id": update.outline_item_info.bid,
                            "status_value": ATTEND_STATUS_NOT_STARTED,
                            "status": attend_status_values[ATTEND_STATUS_NOT_STARTED],
                            **outline_item_info_args,
                        },
                        "",
                    )
                    yield make_script_dto(
                        "lesson_update",
                        {
                            "lesson_id": update.outline_item_info.bid,
                            "status_value": ATTEND_STATUS_IN_PROGRESS,
                            "status": attend_status_values[ATTEND_STATUS_IN_PROGRESS],
                            **outline_item_info_args,
                        },
                        "",
                    )
            elif update.type == _OutlineUpateType.LEAF_COMPLETED:
                current_attend = self._get_current_attend(update.outline_item_info)
                current_attend.status = ATTEND_STATUS_COMPLETED
                db.session.flush()
                yield make_script_dto(
                    "lesson_update",
                    {
                        "lesson_id": update.outline_item_info.bid,
                        "status_value": ATTEND_STATUS_COMPLETED,
                        "status": attend_status_values[ATTEND_STATUS_COMPLETED],
                        **outline_item_info_args,
                    },
                    "",
                )
            elif update.type == _OutlineUpateType.NODE_START:
                # self._outline_item_info = update.outline_item_info
                current_attend = self._get_current_attend(update.outline_item_info)
                current_attend.status = ATTEND_STATUS_IN_PROGRESS
                current_attend.script_index = 0
                db.session.flush()
                yield make_script_dto(
                    "next_chapter",
                    {
                        "lesson_id": update.outline_item_info.bid,
                        "status_value": ATTEND_STATUS_IN_PROGRESS,
                        "status": attend_status_values[ATTEND_STATUS_IN_PROGRESS],
                        **outline_item_info_args,
                    },
                    "",
                )

            elif update.type == _OutlineUpateType.NODE_COMPLETED:
                current_attend = self._get_current_attend(update.outline_item_info)
                current_attend.status = ATTEND_STATUS_COMPLETED
                db.session.flush()
                yield make_script_dto(
                    "chapter_update",
                    {
                        "lesson_id": update.outline_item_info.bid,
                        "status_value": ATTEND_STATUS_COMPLETED,
                        "status": attend_status_values[ATTEND_STATUS_COMPLETED],
                        **outline_item_info_args,
                    },
                    "",
                )

    def _get_default_llm_settings(self) -> LLMSettings:
        return LLMSettings(
            model=self.app.config.get("DEFAULT_LLM_MODEL"),
            temperature=float(self.app.config.get("DEFAULT_LLM_TEMPERATURE")),
        )

    def set_input(self, input: str, input_type: str):
        self._trace_args["input"] = input
        self._trace_args["input_type"] = input_type
        self._input_type = input_type
        self._input = input
        self.app.logger.info(f"set_input {input} {input_type}")

    def _get_goto_attend(
        self,
        block_dto: BlockDTO,
        user_info: User,
        outline_item_info: ShifuOutlineItemDto,
    ) -> AICourseLessonAttend:
        goto: GotoDTO = block_dto.block_content
        variable_id = block_dto.variable_bids[0] if block_dto.variable_bids else ""
        if not variable_id:
            return None
        user_variable = get_user_variable_by_variable_id(
            self.app, user_info.user_id, variable_id
        )

        if not user_variable:
            return None
        destination_condition: GotoConditionDTO = None
        for condition in goto.conditions:
            if condition.value == user_variable:
                destination_condition = condition
                break
        if not destination_condition:
            return None

        self.app.logger.info(
            f"user_variable: {user_variable} find destination {destination_condition.destination_bid}"
        )
        goto_attend = AICourseLessonAttend.query.filter(
            AICourseLessonAttend.user_id == user_info.user_id,
            AICourseLessonAttend.course_id == outline_item_info.shifu_bid,
            AICourseLessonAttend.lesson_id == destination_condition.destination_bid,
            AICourseLessonAttend.status != ATTEND_STATUS_RESET,
        ).first()
        if not goto_attend:
            goto_attend = AICourseLessonAttend()
            goto_attend.user_id = user_info.user_id
            goto_attend.course_id = outline_item_info.shifu_bid
            goto_attend.lesson_id = destination_condition.destination_bid
            goto_attend.attend_id = generate_id(self.app)
            goto_attend.status = ATTEND_STATUS_IN_PROGRESS
            goto_attend.script_index = 0
            db.session.add(goto_attend)
            db.session.flush()
        return goto_attend

    def _get_outline_struct(self, outline_item_id: str) -> HistoryItem:
        q = queue.Queue()
        q.put(self._struct)
        outline_struct = None
        while not q.empty():
            item = q.get()
            if item.bid == outline_item_id:
                outline_struct = item
                break
            if item.children:
                for child in item.children:
                    q.put(child)
        return outline_struct

    def _get_run_script_info(self, attend: AICourseLessonAttend) -> RunScriptInfo:

        outline_item_id = attend.lesson_id
        outline_item_info: ShifuOutlineItemDto = get_outline_item_dto(
            self.app, outline_item_id, self._preview_mode
        )

        outline_struct = self._get_outline_struct(outline_item_id)

        self.app.logger.info(f"outline_struct: {outline_struct}")

        if attend.script_index >= len(outline_struct.children):
            return None
        block_id = outline_struct.children[attend.script_index].id
        block_info: Union[ShifuDraftBlock, ShifuPublishedBlock] = (
            self._block_model.query.filter(
                self._block_model.id == block_id,
            ).first()
        )
        if not block_info:
            raise_error("LESSON.LESSON_NOT_FOUND_IN_COURSE")
        block_dto = generate_block_dto_from_model_internal(block_info)
        if block_dto.type == "goto":
            goto_attend = self._get_goto_attend(
                block_dto, self._user_info, outline_item_info
            )
            goto_outline_struct = self._get_outline_struct(goto_attend.lesson_id)
            if goto_attend.script_index >= len(goto_outline_struct.children):
                attend.script_index = attend.script_index + 1
                db.session.flush()
                ret = self._get_run_script_info(attend)
                if ret:
                    return ret
            return self._get_run_script_info(goto_attend)
        return RunScriptInfo(
            attend=attend,
            outline_item_info=outline_item_info,
            block_dto=block_dto,
        )

    def run(self, app: Flask) -> Generator[str, None, None]:
        app.logger.info(
            f"run_context.run {self._current_attend.script_index} {self._current_attend.status}"
        )
        yield make_script_dto("teacher_avatar", self._shifu_info.avatar, "")
        if not self._current_attend:
            self._current_attend = self._get_current_attend(self._outline_item_info)
        outline_updates = self._get_next_outline_item()
        if len(outline_updates) > 0:
            yield from self._render_outline_updates(outline_updates)
            db.session.flush()
            if self._current_attend.status != ATTEND_STATUS_IN_PROGRESS:
                self._can_continue = False
                return
        app.logger.info(
            f"block type: {self._current_outline_item.bid} {self._current_attend.script_index}"
        )

        run_script_info: RunScriptInfo = self._get_run_script_info(self._current_attend)
        app.logger.info(
            f"block type: {run_script_info.block_dto.type} {self._input_type}"
        )

        if self._run_type == RunType.INPUT:
            res = handle_block_input(
                app=app,
                user_info=self._user_info,
                attend_id=run_script_info.attend.attend_id,
                input=self._input,
                outline_item_info=run_script_info.outline_item_info,
                block_dto=run_script_info.block_dto,
                trace_args=self._trace_args,
                trace=self._trace,
            )
            if res:
                yield from res
            self._can_continue = True
            if run_script_info.block_dto.type != "content":
                run_script_info.attend.script_index += 1
            run_script_info.attend.status = ATTEND_STATUS_IN_PROGRESS
            self._input_type = "continue"
            self._run_type = RunType.OUTPUT
            db.session.flush()
        else:
            app.logger.info(f"handle_block_output {run_script_info.block_dto.type}")
            res = handle_block_output(
                app=app,
                user_info=self._user_info,
                attend_id=run_script_info.attend.attend_id,
                outline_item_info=run_script_info.outline_item_info,
                block_dto=run_script_info.block_dto,
                trace_args=self._trace_args,
                trace=self._trace,
            )
            if res:
                yield from res
            self._current_attend.status = ATTEND_STATUS_IN_PROGRESS
            self._input_type = "continue"
            self._run_type = RunType.OUTPUT
            app.logger.info(f"output block type: {run_script_info.block_dto.type}")
            self._can_continue = check_block_continue(
                app=app,
                user_info=self._user_info,
                attend_id=run_script_info.attend.attend_id,
                outline_item_info=run_script_info.outline_item_info,
                block_dto=run_script_info.block_dto,
                trace_args=self._trace_args,
                trace=self._trace,
            )
            if self._can_continue:
                run_script_info.attend.script_index += 1
            db.session.flush()
        outline_updates = self._get_next_outline_item()
        if len(outline_updates) > 0:
            yield from self._render_outline_updates(outline_updates)
            self._can_continue = False
            db.session.flush()
        # self._trace_args["output"] = run_script_info.block_dto.block_content
        self._trace.update(**self._trace_args)

        # self._trace_args["output"] = block_info.content

        # self._run_type = RunType.OUTPUT

    def has_next(self) -> bool:
        self.app.logger.info(f"has_next {self._can_continue}")
        return self._can_continue

    def get_system_prompt(self, outline_item_info: ShifuOutlineItemDto) -> str:
        path = find_node_with_parents(self._struct, outline_item_info.bid)
        self.app.logger.info(f"path: {path}")
        path = list(reversed(path))
        outline_ids = [item.id for item in path if item.type == "outline"]
        shifu_ids = [item.id for item in path if item.type == "shifu"]
        outline_item_info_db: Union[
            ShifuDraftOutlineItem, ShifuPublishedOutlineItem
        ] = self._outline_model.query.filter(
            self._outline_model.id.in_(outline_ids),
            self._outline_model.deleted == 0,
        ).all()
        outline_item_info_map: dict[
            str, Union[ShifuDraftOutlineItem, ShifuPublishedOutlineItem]
        ] = {o.id: o for o in outline_item_info_db}
        for id in outline_ids:
            outline_item_info = outline_item_info_map.get(id, None)
            if outline_item_info and outline_item_info.llm_system_prompt:
                return outline_item_info.llm_system_prompt
        shifu_info_db: Union[ShifuDraftShifu, ShifuPublishedShifu] = (
            self._shifu_model.query.filter(
                self._shifu_model.id.in_(shifu_ids),
                self._shifu_model.deleted == 0,
            ).first()
        )
        if shifu_info_db and shifu_info_db.llm_system_prompt:
            return shifu_info_db.llm_system_prompt
        return None

    def get_llm_settings(self, outline_item_info: ShifuOutlineItemDto) -> LLMSettings:
        self.app.logger.info(f"get_llm_settings {outline_item_info.bid}")
        self.app.logger.info(f"struct: {self._struct}")
        path = find_node_with_parents(self._struct, outline_item_info.bid)
        self.app.logger.info(f"path: {path}")
        path.reverse()
        self.app.logger.info(f"path: {path}")
        outline_ids = [item.id for item in path if item.type == "outline"]
        shifu_ids = [item.id for item in path if item.type == "shifu"]
        outline_item_info_db: Union[
            ShifuDraftOutlineItem, ShifuPublishedOutlineItem
        ] = self._outline_model.query.filter(
            self._outline_model.id.in_(outline_ids),
            self._outline_model.deleted == 0,
        ).all()
        outline_item_info_map = {o.id: o for o in outline_item_info_db}
        for id in outline_ids:
            outline_item_info = outline_item_info_map.get(id, None)
            if outline_item_info and outline_item_info.llm:
                return LLMSettings(
                    model=outline_item_info.llm,
                    temperature=outline_item_info.llm_temperature,
                )
        shifu_info_db: Union[ShifuDraftShifu, ShifuPublishedShifu] = (
            self._shifu_model.query.filter(
                self._shifu_model.id.in_(shifu_ids),
                self._shifu_model.deleted == 0,
            ).first()
        )
        if shifu_info_db and shifu_info_db.llm:
            return LLMSettings(
                model=shifu_info_db.llm, temperature=shifu_info_db.llm_temperature
            )
        return self._get_default_llm_settings()
