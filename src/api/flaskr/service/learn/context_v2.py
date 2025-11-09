import queue
import threading
from typing import Generator, Union
from enum import Enum
from flaskr.service.learn.const import (
    ROLE_STUDENT,
    ROLE_TEACHER,
    CONTEXT_INTERACTION_NEXT,
)
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
)
from markdown_flow import (
    MarkdownFlow,
    ProcessMode,
    LLMProvider,
    BlockType,
    InteractionParser,
)
from flask import Flask
from flaskr.dao import db
from flaskr.service.shifu.shifu_struct_manager import (
    ShifuOutlineItemDto,
    ShifuInfoDto,
    OutlineItemDtoWithMdflow,
    get_outline_item_dto_with_mdflow,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    PublishedOutlineItem,
    DraftShifu,
    PublishedShifu,
)
from flaskr.service.learn.models import LearnProgressRecord, LearnGeneratedBlock
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from langfuse.client import StatefulTraceClient
from ...api.langfuse import langfuse_client as langfuse, MockClient
from flaskr.service.common import raise_error
from flaskr.service.order.consts import (
    LEARN_STATUS_RESET,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_LOCKED,
)
from flaskr.service.shifu.consts import (
    UNIT_TYPE_VALUE_TRIAL,
    UNIT_TYPE_VALUE_NORMAL,
)

from flaskr.service.user.repository import UserAggregate
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.util import generate_id
from flaskr.service.profile.funcs import get_user_profiles
from flaskr.service.learn.learn_dtos import (
    RunMarkdownFlowDTO,
    GeneratedType,
    OutlineItemUpdateDTO,
    LearnStatus,
)
from flaskr.api.llm import invoke_llm
from flaskr.service.learn.handle_input_ask import handle_input_ask
from flaskr.service.profile.funcs import save_user_profiles, ProfileToSave
from flaskr.service.profile.profile_manage import (
    get_profile_item_definition_list,
    ProfileItemDefinition,
)
from flaskr.service.learn.learn_dtos import VariableUpdateDTO
from flaskr.service.learn.check_text import check_text_with_llm_response
from flaskr.service.learn.llmsetting import LLMSettings
from flaskr.service.learn.utils_v2 import init_generated_block
from flaskr.service.learn.exceptions import PaidException
from flaskr.i18n import _
from flaskr.service.user.exceptions import UserNotLoginException

context_local = threading.local()


class RunType(Enum):
    INPUT = "input"
    OUTPUT = "output"


class RunScriptInfo:
    attend: LearnProgressRecord
    outline_bid: str
    block_position: int
    mdflow: str

    def __init__(
        self,
        attend: LearnProgressRecord,
        outline_bid: str,
        block_position: int,
        mdflow: str,
    ):
        self.attend = attend
        self.outline_bid = outline_bid
        self.block_position = block_position
        self.mdflow = mdflow


class RUNLLMProvider(LLMProvider):
    app: Flask
    llm_settings: LLMSettings
    trace: StatefulTraceClient
    trace_args: dict

    def __init__(
        self,
        app: Flask,
        llm_settings: LLMSettings,
        trace: StatefulTraceClient,
        trace_args: dict,
    ):
        self.app = app
        self.llm_settings = llm_settings
        self.trace = trace
        self.trace_args = trace_args

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        # Extract the last message content as the main prompt
        if not messages:
            raise ValueError("No messages provided")

        # Get the last message content
        system_prompt = messages[0].get("content", "")
        last_message = messages[-1]
        prompt = last_message.get("content", "")

        # Use provided model/temperature or fall back to settings
        actual_model = model or self.llm_settings.model
        actual_temperature = (
            temperature if temperature is not None else self.llm_settings.temperature
        )

        res = invoke_llm(
            self.app,
            self.trace_args.get("user_id", ""),
            self.trace,
            message=prompt,
            system=system_prompt,
            model=actual_model,
            stream=False,
            generation_name="run_llm",
            temperature=actual_temperature,
        )
        # Collect all stream responses and concatenate the results
        content_parts = []
        for response in res:
            if response.result:
                content_parts.append(response.result)
        return "".join(content_parts)

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Generator[str, None, None]:
        # Extract the last message content as the main prompt
        if not messages:
            raise ValueError("No messages provided")

        system_prompt = messages[0].get("content", "")
        # Get the last message content
        last_message = messages[-1]
        prompt = last_message.get("content", "")

        # Use provided model/temperature or fall back to settings
        actual_model = model or self.llm_settings.model
        actual_temperature = (
            temperature if temperature is not None else self.llm_settings.temperature
        )

        # Check if there's a system message
        self.app.logger.info("stream invoke_llm begin")
        res = invoke_llm(
            self.app,
            self.trace_args["user_id"],
            self.trace,
            message=prompt,
            system=system_prompt,
            model=actual_model,
            stream=True,
            generation_name="run_llm",
            temperature=actual_temperature,
        )
        self.app.logger.info(f"stream invoke_llm res: {res}")
        first_result = False
        for i in res:
            if i.result:
                if not first_result:
                    first_result = True
                    self.app.logger.info(f"stream first result: {i.result}")
                yield i.result
        self.app.logger.info("stream invoke_llm end")


class RunScriptContextV2:
    user_id: str
    attend_id: str
    is_paid: bool

    preview_mode: bool
    _q: queue.Queue
    _outline_item_info: ShifuOutlineItemDto
    _struct: HistoryItem
    _user_info: UserAggregate
    _is_paid: bool
    _preview_mode: bool
    _shifu_ids: list[str]
    _run_type: RunType
    _app: Flask
    _shifu_model: Union[DraftShifu, PublishedShifu]
    _outline_model: Union[DraftOutlineItem, PublishedOutlineItem]
    _trace_args: dict
    _shifu_info: ShifuInfoDto
    _trace: Union[StatefulTraceClient, MockClient]
    _input_type: str
    _input: str
    _can_continue: bool
    _last_position: int

    def __init__(
        self,
        app: Flask,
        shifu_info: ShifuInfoDto,
        struct: HistoryItem,
        outline_item_info: ShifuOutlineItemDto,
        user_info: UserAggregate,
        is_paid: bool,
        preview_mode: bool,
    ):
        self._last_position = -1
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
            self._outline_model = DraftOutlineItem
            self._shifu_model = DraftShifu
        else:
            self._outline_model = PublishedOutlineItem
            self._shifu_model = PublishedShifu
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
        self._current_attend = None
        self._trace_args = {}
        self._trace_args["user_id"] = user_info.user_id
        self._trace_args["input"] = ""
        self._trace_args["name"] = self._outline_item_info.title
        self._trace = langfuse.trace(**self._trace_args)
        self._trace_args["output"] = ""
        context_local.current_context = self

    @staticmethod
    def get_current_context(app: Flask) -> Union["RunScriptContextV2", None]:
        if not hasattr(context_local, "current_context"):
            return None
        return context_local.current_context

    def _get_current_attend(self, outline_bid: str) -> LearnProgressRecord:
        attend_info: LearnProgressRecord = (
            LearnProgressRecord.query.filter(
                LearnProgressRecord.outline_item_bid == outline_bid,
                LearnProgressRecord.user_bid == self._user_info.user_id,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
            )
            .order_by(LearnProgressRecord.id.desc())
            .first()
        )
        if not attend_info:
            outline_item_info_db: Union[DraftOutlineItem, PublishedOutlineItem] = (
                self._outline_model.query.filter(
                    self._outline_model.outline_item_bid == outline_bid,
                    self._outline_model.deleted == 0,
                )
                .order_by(self._outline_model.id.desc())
                .first()
            )
            if not outline_item_info_db:
                raise_error("server.shifu.lessonNotFoundInCourse")
            if outline_item_info_db.type == UNIT_TYPE_VALUE_NORMAL:
                if (not self._is_paid) and (not self._preview_mode):
                    raise PaidException()
            elif outline_item_info_db.type == UNIT_TYPE_VALUE_TRIAL:
                if not self._user_info.mobile:
                    raise UserNotLoginException()
            parent_path = find_node_with_parents(self._struct, outline_bid)
            attend_info = None
            for item in parent_path:
                if item.type == "outline":
                    attend_info = LearnProgressRecord.query.filter(
                        LearnProgressRecord.outline_item_bid == item.bid,
                        LearnProgressRecord.user_bid == self._user_info.user_id,
                        LearnProgressRecord.status != LEARN_STATUS_RESET,
                    ).first()
                    if attend_info:
                        continue
                    attend_info = LearnProgressRecord()
                    attend_info.outline_item_bid = outline_item_info_db.outline_item_bid
                    attend_info.shifu_bid = outline_item_info_db.shifu_bid
                    attend_info.user_bid = self._user_info.user_id
                    attend_info.status = LEARN_STATUS_NOT_STARTED
                    attend_info.progress_record_bid = generate_id(self.app)
                    attend_info.block_position = 0
                    db.session.add(attend_info)
                    db.session.flush()
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

    # get the outline items to start or complete
    def _get_next_outline_item(self) -> list[OutlineItemUpdateDTO]:
        res = []
        q = queue.Queue()
        q.put(self._struct)
        outline_ids = []
        while not q.empty():
            item: HistoryItem = q.get()
            if item.type == "outline":
                outline_ids.append(item.bid)
            if item.children:
                for child in item.children:
                    q.put(child)
        outline_item_info_db: list[tuple[str, bool, str]] = (
            db.session.query(
                self._outline_model.outline_item_bid,
                self._outline_model.hidden,
                self._outline_model.title,
            )
            .filter(
                self._outline_model.outline_item_bid.in_(outline_ids),
                self._outline_model.deleted == 0,
            )
            .all()
        )
        outline_item_hidden_map: dict[str, bool] = {
            bid: hidden for bid, hidden, _title in outline_item_info_db
        }
        outline_item_title_map: dict[str, str] = {
            bid: title for bid, _hidden, title in outline_item_info_db
        }

        def _mark_sub_node_completed(
            outline_item_info: HistoryItem, res: list[OutlineItemUpdateDTO]
        ):
            q = queue.Queue()
            q.put(self._struct)
            if self._is_leaf_outline_item(outline_item_info):
                res.append(
                    OutlineItemUpdateDTO(
                        outline_bid=outline_item_info.bid,
                        title=outline_item_title_map.get(outline_item_info.bid, ""),
                        status=LearnStatus.COMPLETED,
                        has_children=False,
                    )
                )
            else:
                res.append(
                    OutlineItemUpdateDTO(
                        outline_bid=outline_item_info.bid,
                        title=outline_item_title_map.get(outline_item_info.bid, ""),
                        status=LearnStatus.COMPLETED,
                        has_children=True,
                    )
                )
            while not q.empty():
                item: HistoryItem = q.get()
                if item.children and outline_item_info.bid in [
                    child.bid for child in item.children
                ]:
                    index = [child.bid for child in item.children].index(
                        outline_item_info.bid
                    )
                    while index < len(item.children) - 1:
                        # not sub node
                        current_node = item.children[index + 1]
                        if outline_item_hidden_map.get(current_node.bid, True):
                            index += 1
                            continue
                        while (
                            current_node.children
                            and current_node.children[0].type == "outline"
                        ):
                            res.append(
                                OutlineItemUpdateDTO(
                                    outline_bid=current_node.bid,
                                    title=outline_item_title_map.get(
                                        current_node.bid, ""
                                    ),
                                    status=LearnStatus.IN_PROGRESS,
                                    has_children=True,
                                )
                            )
                            current_node = current_node.children[0]
                        res.append(
                            OutlineItemUpdateDTO(
                                outline_bid=current_node.bid,
                                title=outline_item_title_map.get(current_node.bid, ""),
                                status=LearnStatus.IN_PROGRESS,
                                has_children=False,
                            )
                        )
                        return
                    if index == len(item.children) - 1 and item.type == "outline":
                        _mark_sub_node_completed(item, res)
                if item.children and item.children[0].type == "outline":
                    for child in item.children:
                        q.put(child)

        def _mark_sub_node_start(
            outline_item_info: HistoryItem, res: list[OutlineItemUpdateDTO]
        ):
            path = find_node_with_parents(self._struct, outline_item_info.bid)
            for item in path:
                if item.type == "outline":
                    if item.children and item.children[0].type == "outline":
                        res.append(
                            OutlineItemUpdateDTO(
                                outline_bid=item.bid,
                                title=outline_item_title_map.get(item.bid, ""),
                                status=LearnStatus.IN_PROGRESS,
                                has_children=True,
                            )
                        )
                    else:
                        res.append(
                            OutlineItemUpdateDTO(
                                outline_bid=item.bid,
                                title=outline_item_title_map.get(item.bid, ""),
                                status=LearnStatus.IN_PROGRESS,
                                has_children=False,
                            )
                        )

        if self._current_attend.block_position >= max(
            len(self._current_outline_item.children),
            self._current_outline_item.child_count,
        ):
            _mark_sub_node_completed(self._current_outline_item, res)
        if self._current_attend.status == LEARN_STATUS_NOT_STARTED:
            _mark_sub_node_start(self._current_outline_item, res)
        return res

    def _get_current_outline_item(self) -> ShifuOutlineItemDto:
        return self._current_outline_item

    def _render_outline_updates(
        self, outline_updates: list[OutlineItemUpdateDTO], new_chapter: bool = False
    ) -> Generator[str, None, None]:
        shifu_bids = [o.outline_bid for o in outline_updates]
        outline_item_info_db: Union[DraftOutlineItem, PublishedOutlineItem] = (
            self._outline_model.query.filter(
                self._outline_model.outline_item_bid.in_(shifu_bids),
                self._outline_model.deleted == 0,
            ).all()
        )
        outline_item_info_map: dict[
            str, Union[DraftOutlineItem, PublishedOutlineItem]
        ] = {o.outline_item_bid: o for o in outline_item_info_db}
        for update in outline_updates:
            outline_item_info = outline_item_info_map.get(update.outline_bid, None)
            if not outline_item_info:
                continue
            if outline_item_info.hidden:
                continue
            if (not update.has_children) and update.status == LearnStatus.IN_PROGRESS:
                self._current_outline_item = self._get_outline_struct(
                    update.outline_bid
                )
                if self._current_attend.outline_item_bid == update.outline_bid:
                    self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                    self._current_attend.outline_item_updated = 0
                    self._current_attend.block_position = 0
                    yield RunMarkdownFlowDTO(
                        outline_bid=update.outline_bid,
                        generated_block_bid="",
                        type=GeneratedType.OUTLINE_ITEM_UPDATE,
                        content=update,
                    )
                    db.session.flush()
                    continue
                self._current_attend = self._get_current_attend(update.outline_bid)
                if (
                    self._current_attend.status == LEARN_STATUS_NOT_STARTED
                    or self._current_attend.status == LEARN_STATUS_LOCKED
                ):
                    self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                    self._current_attend.block_position = 0
                    db.session.flush()
                yield RunMarkdownFlowDTO(
                    outline_bid=update.outline_bid,
                    generated_block_bid="",
                    type=GeneratedType.OUTLINE_ITEM_UPDATE,
                    content=update,
                )
            elif (not update.has_children) and update.status == LearnStatus.COMPLETED:
                current_attend = self._get_current_attend(update.outline_bid)
                current_attend.status = LEARN_STATUS_COMPLETED
                self._current_attend = current_attend
                db.session.flush()
                yield RunMarkdownFlowDTO(
                    outline_bid=update.outline_bid,
                    generated_block_bid="",
                    type=GeneratedType.OUTLINE_ITEM_UPDATE,
                    content=update,
                )
            elif update.has_children and update.status == LearnStatus.IN_PROGRESS:
                if new_chapter:
                    status = LEARN_STATUS_NOT_STARTED
                else:
                    status = LEARN_STATUS_IN_PROGRESS
                current_attend = self._get_current_attend(update.outline_bid)
                current_attend.status = status
                current_attend.block_position = 0

                db.session.flush()

                yield RunMarkdownFlowDTO(
                    outline_bid=update.outline_bid,
                    generated_block_bid="",
                    type=GeneratedType.OUTLINE_ITEM_UPDATE,
                    content=update,
                )
            elif update.has_children and update.status == LearnStatus.COMPLETED:
                current_attend = self._get_current_attend(update.outline_bid)
                current_attend.status = LEARN_STATUS_COMPLETED
                db.session.flush()
                yield RunMarkdownFlowDTO(
                    outline_bid=update.outline_bid,
                    generated_block_bid="",
                    type=GeneratedType.OUTLINE_ITEM_UPDATE,
                    content=update,
                )

    def _emit_next_chapter_interaction(
        self,
    ) -> Generator[RunMarkdownFlowDTO, None, None]:
        """
        Persist and emit the standardized `_sys_next_chapter` interaction when a lesson
        completes so the frontend can advance automatically.
        """
        if not self._current_attend or not self._outline_item_info:
            return
        button_label = _("server.learn.nextChapterButton")
        button_md = f"?[{button_label}//{CONTEXT_INTERACTION_NEXT}]({button_label})"
        existing_block = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid
                == self._current_attend.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid
                == self._current_attend.outline_item_bid,
                LearnGeneratedBlock.user_bid == self._user_info.user_id,
                LearnGeneratedBlock.type == BLOCK_TYPE_MDINTERACTION_VALUE,
                LearnGeneratedBlock.status == 1,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.block_content_conf == button_md,
            )
            .order_by(LearnGeneratedBlock.id.desc())
            .first()
        )
        if existing_block:
            return
        generated_block: LearnGeneratedBlock = init_generated_block(
            self.app,
            shifu_bid=self._current_attend.shifu_bid,
            outline_item_bid=self._current_attend.outline_item_bid,
            progress_record_bid=self._current_attend.progress_record_bid,
            user_bid=self._user_info.user_id,
            block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
            mdflow=button_md,
            block_index=self._current_attend.block_position,
        )
        generated_block.role = ROLE_TEACHER
        generated_block.block_content_conf = button_md
        db.session.add(generated_block)
        db.session.flush()
        yield RunMarkdownFlowDTO(
            outline_bid=self._current_attend.outline_item_bid,
            generated_block_bid=generated_block.generated_block_bid,
            type=GeneratedType.INTERACTION,
            content=button_md,
        )

    def _get_default_llm_settings(self) -> LLMSettings:
        return LLMSettings(
            model=self.app.config.get("DEFAULT_LLM_MODEL"),
            temperature=float(self.app.config.get("DEFAULT_LLM_TEMPERATURE")),
        )

    def set_input(self, input: str | dict, input_type: str):
        """
        Set user input.

        Args:
            input: User input, can be:
                   - str: legacy format (e.g., "Python")
                   - dict: new format from markdown-flow 0.2.27+ (e.g., {"lang": ["Python"]})
            input_type: Input type
        """
        self._trace_args["input"] = input
        self._trace_args["input_type"] = input_type
        self._input_type = input_type
        self._input = input

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

    def _get_run_script_info(self, attend: LearnProgressRecord) -> RunScriptInfo:
        outline_item_id = attend.outline_item_bid
        outline_item_info: OutlineItemDtoWithMdflow = get_outline_item_dto_with_mdflow(
            self.app, outline_item_id, self._preview_mode
        )

        self.app.logger.info(f"outline_item_info: {outline_item_info.mdflow}")

        mddoc = MarkdownFlow(outline_item_info.mdflow)
        block_list = mddoc.get_all_blocks()
        self.app.logger.info(
            f"attend position: {attend.block_position} blocks:{len(block_list)}"
        )
        if attend.block_position >= len(block_list):
            return None
        return RunScriptInfo(
            attend=attend,
            outline_bid=outline_item_info.outline_bid,
            block_position=attend.block_position,
            mdflow=outline_item_info.mdflow,
        )

    def _get_run_script_info_by_block_id(self, block_id: str) -> RunScriptInfo:
        generate_block: LearnGeneratedBlock = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == block_id,
            LearnGeneratedBlock.deleted == 0,
        ).first()
        if not generate_block:
            raise_error("server.shifu.lessonNotFoundInCourse")
        outline_item_info: OutlineItemDtoWithMdflow = get_outline_item_dto_with_mdflow(
            self.app, generate_block.outline_item_bid, self._preview_mode
        )
        attend: LearnProgressRecord = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == self._user_info.user_id,
            LearnProgressRecord.shifu_bid == outline_item_info.shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_item_info.bid,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        ).first()
        return RunScriptInfo(
            attend=attend,
            outline_bid=outline_item_info.outline_bid,
            block_position=generate_block.position,
            mdflow=outline_item_info.mdflow,
        )

    def run_inner(self, app: Flask) -> Generator[RunMarkdownFlowDTO, None, None]:
        self._current_attend = self._get_current_attend(self._outline_item_info.bid)
        app.logger.info(
            f"run_context.run {self._current_attend.block_position} {self._current_attend.status}"
        )
        self._trace_args["session_id"] = self._current_attend.progress_record_bid
        outline_updates = self._get_next_outline_item()
        if len(outline_updates) > 0:
            yield from self._render_outline_updates(outline_updates, new_chapter=False)
            db.session.flush()
            self._current_attend = self._get_current_attend(self._outline_item_info.bid)
            if self._current_attend.status not in [
                LEARN_STATUS_IN_PROGRESS,
                LEARN_STATUS_NOT_STARTED,
            ]:
                app.logger.info(
                    f"current_attend.status != LEARN_STATUS_IN_PROGRESS To False,current_attend.status: {self._current_attend.status}"
                )
                self._can_continue = False
                return

        run_script_info: RunScriptInfo = self._get_run_script_info(self._current_attend)
        if run_script_info is None:
            self.app.logger.warning("run script is none")
            yield from self._emit_next_chapter_interaction()
            self._can_continue = False
            outline_updates = self._get_next_outline_item()
            if len(outline_updates) > 0:
                yield from self._render_outline_updates(
                    outline_updates, new_chapter=True
                )
                self._can_continue = False
                db.session.flush()
            return
        llm_settings = self.get_llm_settings(run_script_info.outline_bid)
        system_prompt = self.get_system_prompt(run_script_info.outline_bid)
        mdflow = MarkdownFlow(
            document=run_script_info.mdflow,
            document_prompt=system_prompt,
            llm_provider=RUNLLMProvider(
                app, llm_settings, self._trace, self._trace_args
            ),
        )
        block_list = mdflow.get_all_blocks()

        if self._input_type == "ask":
            if self._last_position == -1:
                self._last_position = run_script_info.block_position
            ask_input = self._input
            app.logger.info(f"ask_input: {ask_input}")
            if isinstance(ask_input, dict):
                ask_input = ask_input.get("input", "")
            else:
                ask_input = ask_input
            if isinstance(ask_input, list):
                ask_input = ",".join(ask_input)
            app.logger.info(f"ask_input: {ask_input}")
            res = handle_input_ask(
                app,
                self,
                self._user_info,
                self._current_attend.progress_record_bid,
                ask_input,
                self._outline_item_info,
                self._trace_args,
                self._trace,
                self._preview_mode,
                self._last_position,
            )
            yield from res
            self._can_continue = False
            db.session.flush()
            return

        user_profile = get_user_profiles(
            app, self._user_info.user_id, self._outline_item_info.shifu_bid
        )
        variable_definition: list[ProfileItemDefinition] = (
            get_profile_item_definition_list(
                app, self._user_info.user_id, self._outline_item_info.shifu_bid
            )
        )
        variable_definition_key_id_map: dict[str, str] = {
            p.profile_key: p.profile_id for p in variable_definition
        }

        if run_script_info.block_position >= len(block_list):
            outline_updates = self._get_next_outline_item()
            if len(outline_updates) > 0:
                yield from self._render_outline_updates(
                    outline_updates, new_chapter=True
                )
                self._can_continue = False
                db.session.flush()
            return
        block = block_list[run_script_info.block_position]
        app.logger.info(f"block: {block}")
        app.logger.info(f"self._run_type: {self._run_type}")
        if self._run_type == RunType.INPUT:
            if block.block_type != BlockType.INTERACTION:
                self._can_continue = True
                self._run_type = RunType.OUTPUT
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                db.session.flush()
                return
            interaction_parser: InteractionParser = InteractionParser()
            parsed_interaction = interaction_parser.parse(block.content)
            generated_block: LearnGeneratedBlock = (
                LearnGeneratedBlock.query.filter(
                    LearnGeneratedBlock.progress_record_bid
                    == run_script_info.attend.progress_record_bid,
                    LearnGeneratedBlock.outline_item_bid == run_script_info.outline_bid,
                    LearnGeneratedBlock.user_bid == self._user_info.user_id,
                    LearnGeneratedBlock.type == BLOCK_TYPE_MDINTERACTION_VALUE,
                    LearnGeneratedBlock.position == run_script_info.block_position,
                    LearnGeneratedBlock.status == 1,
                )
                .order_by(LearnGeneratedBlock.id.desc())
                .first()
            )
            if (
                parsed_interaction.get("buttons")
                and len(parsed_interaction.get("buttons")) > 0
            ):
                for button in parsed_interaction.get("buttons"):
                    if button.get("value") == "_sys_pay":
                        if not self._is_paid:
                            yield RunMarkdownFlowDTO(
                                outline_bid=run_script_info.outline_bid,
                                generated_block_bid=generated_block.generated_block_bid
                                if generated_block
                                else generate_id(app),
                                type=GeneratedType.INTERACTION,
                                content=block.content,
                            )
                            self._can_continue = False
                            db.session.flush()
                            return
                        else:
                            self._can_continue = True
                            self._current_attend.block_position += 1
                            self._run_type = RunType.OUTPUT
                            db.session.flush()
                            return
                    if button.get("value") == "_sys_login":
                        if bool(self._user_info.mobile):
                            self._can_continue = True
                            self._current_attend.block_position += 1
                            self._run_type = RunType.OUTPUT
                            db.session.flush()
                            return
                        else:
                            yield RunMarkdownFlowDTO(
                                outline_bid=run_script_info.outline_bid,
                                generated_block_bid=generated_block.generated_block_bid
                                if generated_block
                                else generate_id(app),
                                type=GeneratedType.INTERACTION,
                                content=block.content,
                            )
                            self._can_continue = False
                            db.session.flush()
                            return
            if not generated_block:
                generated_block = init_generated_block(
                    app,
                    shifu_bid=run_script_info.attend.shifu_bid,
                    outline_item_bid=run_script_info.outline_bid,
                    progress_record_bid=run_script_info.attend.progress_record_bid,
                    user_bid=self._user_info.user_id,
                    block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
                    mdflow=block.content,
                    block_index=run_script_info.block_position,
                )
                app.logger.info(
                    f"generated_block not found, init new one: {generated_block.generated_block_bid}"
                )
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.INTERACTION,
                    content=block.content,
                )
                self._can_continue = False
                db.session.add(generated_block)
                db.session.flush()
                return
            # Convert dict to string for database storage (markdown-flow 0.2.27+ sends dict)
            if isinstance(self._input, dict):
                # Convert {"var": ["val1", "val2"]} to "val1,val2" or just "val1"
                values = []
                for v in self._input.values():
                    if isinstance(v, list):
                        # Filter out None and convert to string
                        values.extend([str(item) for item in v if item is not None])
                    elif v is not None:
                        values.append(str(v))
                generated_block.generated_content = ",".join(values) if values else ""
            else:
                generated_block.generated_content = (
                    str(self._input) if self._input is not None else ""
                )
            generated_block.role = ROLE_STUDENT
            generated_block.position = run_script_info.block_position
            generated_block.block_content_conf = block.content
            generated_block.status = 1
            db.session.flush()
            res = check_text_with_llm_response(
                app,
                self._user_info,
                generated_block,
                generated_block.generated_content,  # Use converted string value
                self._trace,
                self._outline_item_info.bid,
                self._outline_item_info.position,
                self._outline_item_info.shifu_bid,
                llm_settings,
                self._current_attend.progress_record_bid,
                "",
            )
            # Check if the generator yields any content (not None)
            has_content = False
            for i in res:
                if i is not None and i != "":
                    self.app.logger.info(f"check_text_with_llm_response: {i}")
                    has_content = True
                    yield RunMarkdownFlowDTO(
                        outline_bid=run_script_info.outline_bid,
                        generated_block_bid=generated_block.generated_block_bid,
                        type=GeneratedType.CONTENT,
                        content=i,
                    )

            if has_content:
                self._can_continue = False
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.BREAK,
                    content="",
                )
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.INTERACTION,
                    content=block.content,
                )

                db.session.flush()
                return
            if not parsed_interaction.get("variable"):
                self._can_continue = True
                self._run_type = RunType.OUTPUT
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                self._current_attend.block_position += 1
                db.session.flush()
                return
            # Direct synchronous call - no async wrapper needed (markdown-flow 0.2.27+)
            # Prepare user_input based on input type
            if isinstance(self._input, dict):
                # Already in dict format from frontend, but need to filter out None values
                user_input_param = {}
                for key, value in self._input.items():
                    if isinstance(value, list):
                        # Filter out None values and ensure all are strings
                        cleaned = [str(v) for v in value if v is not None]
                        if cleaned:  # Only add if there are non-None values
                            user_input_param[key] = cleaned
                    elif value is not None:
                        user_input_param[key] = [str(value)]
            else:
                # Legacy string format, wrap it
                if self._input is not None:
                    user_input_param = {
                        parsed_interaction.get("variable", "input"): [str(self._input)]
                    }
                else:
                    user_input_param = {}

            validate_result = mdflow.process(
                run_script_info.block_position,
                ProcessMode.COMPLETE,
                user_input=user_input_param,
            )

            if (
                validate_result.variables is not None
                and len(validate_result.variables) > 0
            ):
                profile_to_save: list[ProfileToSave] = []
                for key, value in validate_result.variables.items():
                    profile_id = variable_definition_key_id_map.get(key, "")
                    # Convert list to string (markdown-flow 0.2.27+ returns list[str] for multi-select)
                    if isinstance(value, list):
                        # Filter out None and convert to string
                        value_str = ",".join(
                            [str(item) for item in value if item is not None]
                        )
                    else:
                        value_str = str(value) if value is not None else ""
                    profile_to_save.append(ProfileToSave(key, value_str, profile_id))

                save_user_profiles(
                    app,
                    self._user_info.user_id,
                    self._outline_item_info.shifu_bid,
                    profile_to_save,
                )
                for profile in profile_to_save:
                    yield RunMarkdownFlowDTO(
                        outline_bid=run_script_info.outline_bid,
                        generated_block_bid=generated_block.generated_block_bid,
                        type=GeneratedType.VARIABLE_UPDATE,
                        content=VariableUpdateDTO(
                            variable_name=profile.key,
                            variable_value=profile.value,
                        ),
                    )
                self._can_continue = True
                self._current_attend.block_position += 1
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                self._run_type = RunType.OUTPUT
                self.app.logger.warning(
                    f"passed and position: {self._current_attend.block_position}"
                )
                db.session.flush()
                return
            else:
                generated_block: LearnGeneratedBlock = init_generated_block(
                    app,
                    shifu_bid=run_script_info.attend.shifu_bid,
                    outline_item_bid=run_script_info.outline_bid,
                    progress_record_bid=run_script_info.attend.progress_record_bid,
                    user_bid=self._user_info.user_id,
                    block_type=BLOCK_TYPE_MDERRORMESSAGE_VALUE,
                    mdflow=block.content,
                    block_index=block.index,
                )
                generated_block.type = BLOCK_TYPE_MDERRORMESSAGE_VALUE
                generated_block.block_content_conf = block.content
                generated_block.role = ROLE_TEACHER
                db.session.add(generated_block)
                db.session.flush()
                content = ""
                for i in validate_result.content:
                    content += i
                    yield RunMarkdownFlowDTO(
                        outline_bid=run_script_info.outline_bid,
                        generated_block_bid=generated_block.generated_block_bid,
                        type=GeneratedType.CONTENT,
                        content=i,
                    )
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.BREAK,
                    content="",
                )
                generated_block.generated_content = content
                generated_block.type = BLOCK_TYPE_MDERRORMESSAGE_VALUE
                generated_block.block_content_conf = block.content
                db.session.add(generated_block)
                db.session.flush()
                generated_block: LearnGeneratedBlock = init_generated_block(
                    app,
                    shifu_bid=run_script_info.attend.shifu_bid,
                    outline_item_bid=run_script_info.outline_bid,
                    progress_record_bid=run_script_info.attend.progress_record_bid,
                    user_bid=self._user_info.user_id,
                    block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
                    mdflow=block.content,
                    block_index=block.index,
                )
                generated_block.role = ROLE_TEACHER
                db.session.add(generated_block)
                db.session.flush()
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.INTERACTION,
                    content=block.content,
                )
                self._can_continue = False
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                db.session.add(generated_block)
                db.session.flush()
        elif self._run_type == RunType.OUTPUT:
            generated_block: LearnGeneratedBlock = init_generated_block(
                app,
                shifu_bid=run_script_info.attend.shifu_bid,
                outline_item_bid=run_script_info.outline_bid,
                progress_record_bid=run_script_info.attend.progress_record_bid,
                user_bid=self._user_info.user_id,
                block_type=BLOCK_TYPE_MDINTERACTION_VALUE,
                mdflow=block.content,
                block_index=block.index,
            )
            if block.block_type == BlockType.INTERACTION:
                interaction_parser: InteractionParser = InteractionParser()
                parsed_interaction = interaction_parser.parse(block.content)
                if (
                    parsed_interaction.get("buttons")
                    and len(parsed_interaction.get("buttons")) > 0
                ):
                    for button in parsed_interaction.get("buttons"):
                        if button.get("value") == "_sys_pay":
                            if self._is_paid:
                                self._can_continue = True
                                self._current_attend.block_position += 1
                                self._run_type = RunType.OUTPUT
                                db.session.flush()
                                return
                        if button.get("value") == "_sys_login":
                            self.app.logger.warning(
                                f"_sys_login :{self._user_info.mobile}"
                            )
                            if bool(self._user_info.mobile):
                                self._can_continue = True
                                self._current_attend.block_position += 1
                                self._run_type = RunType.OUTPUT
                                db.session.flush()
                                return
                generated_block.type = BLOCK_TYPE_MDINTERACTION_VALUE
                generated_block.generated_content = ""
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.INTERACTION,
                    content=block.content,
                )
                self._can_continue = False
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                db.session.add(generated_block)
                db.session.flush()
            else:
                generated_block.type = BLOCK_TYPE_MDCONTENT_VALUE
                generated_content = ""

                # Direct synchronous stream processing (markdown-flow 0.2.27+)
                app.logger.info(f"process_stream: {run_script_info.block_position}")
                app.logger.info(f"variables: {user_profile}")

                # For CONTENT blocks, no user_input is needed (only INTERACTION blocks have user input)
                stream_result = mdflow.process(
                    run_script_info.block_position,
                    ProcessMode.STREAM,
                    variables=user_profile,
                )

                # Handle both Generator and single LLMResult (markdown-flow 0.2.27+)
                # In some edge cases (e.g., no LLM provider), returns a single LLMResult instead of Generator
                import inspect

                if inspect.isgenerator(stream_result):
                    # It's a generator, iterate normally
                    for llm_result in stream_result:
                        chunk_content = (
                            llm_result.content
                            if hasattr(llm_result, "content")
                            else str(llm_result)
                        )
                        if chunk_content:
                            generated_content += chunk_content
                            yield RunMarkdownFlowDTO(
                                outline_bid=run_script_info.outline_bid,
                                generated_block_bid=generated_block.generated_block_bid,
                                type=GeneratedType.CONTENT,
                                content=chunk_content,
                            )
                else:
                    # It's a single LLMResult object (edge case)
                    chunk_content = (
                        stream_result.content
                        if hasattr(stream_result, "content")
                        else str(stream_result)
                    )
                    if chunk_content:
                        generated_content += chunk_content
                        yield RunMarkdownFlowDTO(
                            outline_bid=run_script_info.outline_bid,
                            generated_block_bid=generated_block.generated_block_bid,
                            type=GeneratedType.CONTENT,
                            content=chunk_content,
                        )
                yield RunMarkdownFlowDTO(
                    outline_bid=run_script_info.outline_bid,
                    generated_block_bid=generated_block.generated_block_bid,
                    type=GeneratedType.BREAK,
                    content="",
                )
                generated_block.generated_content = generated_content
                db.session.add(generated_block)
                self._can_continue = False
                self._current_attend.status = LEARN_STATUS_IN_PROGRESS
                self._current_attend.block_position += 1
                db.session.flush()
        outline_updates = self._get_next_outline_item()
        if len(outline_updates) > 0:
            yield from self._render_outline_updates(outline_updates, new_chapter=True)
            self._can_continue = False
            db.session.flush()
        self._trace.update(**self._trace_args)

    def run(self, app: Flask) -> Generator[RunMarkdownFlowDTO, None, None]:
        try:
            yield from self.run_inner(app)
        except PaidException:
            app.logger.info("PaidException")
            self._can_continue = False
            yield RunMarkdownFlowDTO(
                outline_bid=self._outline_item_info.bid,
                generated_block_bid=generate_id(self.app),
                type=GeneratedType.INTERACTION,
                content=f"?[{_('server.order.checkout')}//_sys_pay]",
            )
        except UserNotLoginException:
            app.logger.info("UserNotLoginException")
            self._can_continue = False
            yield RunMarkdownFlowDTO(
                outline_bid=self._outline_item_info.bid,
                generated_block_bid=generate_id(self.app),
                type=GeneratedType.INTERACTION,
                content=f"?[{_('USER.LOGIN')}//_sys_login]",
            )

    def has_next(self) -> bool:
        return self._can_continue

    def get_system_prompt(self, outline_item_bid: str) -> str:
        path = find_node_with_parents(self._struct, outline_item_bid)
        path = list(reversed(path))
        outline_ids = [item.id for item in path if item.type == "outline"]
        shifu_ids = [item.id for item in path if item.type == "shifu"]
        outline_item_info_db: Union[DraftOutlineItem, PublishedOutlineItem] = (
            self._outline_model.query.filter(
                self._outline_model.id.in_(outline_ids),
                self._outline_model.deleted == 0,
            ).all()
        )
        outline_item_info_map: dict[
            str, Union[DraftOutlineItem, PublishedOutlineItem]
        ] = {o.id: o for o in outline_item_info_db}
        for id in outline_ids:
            outline_item_info = outline_item_info_map.get(id, None)
            if (
                outline_item_info
                and outline_item_info.llm_system_prompt
                and outline_item_info.llm_system_prompt != ""
            ):
                self.app.logger.info(
                    f"outline_item_info.llm_system_prompt: {outline_item_info.llm_system_prompt}"
                )
                return outline_item_info.llm_system_prompt
        shifu_info_db: Union[DraftShifu, PublishedShifu] = (
            self._shifu_model.query.filter(
                self._shifu_model.id.in_(shifu_ids),
                self._shifu_model.deleted == 0,
            )
            .order_by(self._shifu_model.id.desc())
            .first()
        )
        self.app.logger.info(f"shifu_info_db: {shifu_info_db}")
        if shifu_info_db and shifu_info_db.llm_system_prompt:
            self.app.logger.info(
                f"shifu_info_db.llm_system_prompt: {shifu_info_db.llm_system_prompt}"
            )
            return shifu_info_db.llm_system_prompt
        return None

    def get_llm_settings(self, outline_bid: str) -> LLMSettings:
        path = find_node_with_parents(self._struct, outline_bid)
        path.reverse()
        outline_ids = [item.id for item in path if item.type == "outline"]
        shifu_ids = [item.id for item in path if item.type == "shifu"]
        outline_item_info_db: Union[DraftOutlineItem, PublishedOutlineItem] = (
            self._outline_model.query.filter(
                self._outline_model.id.in_(outline_ids),
                self._outline_model.deleted == 0,
            ).all()
        )
        outline_item_info_map = {o.id: o for o in outline_item_info_db}
        for id in outline_ids:
            outline_item_info = outline_item_info_map.get(id, None)
            if outline_item_info and outline_item_info.llm:
                return LLMSettings(
                    model=outline_item_info.llm,
                    temperature=outline_item_info.llm_temperature,
                )
        shifu_info_db: Union[DraftShifu, PublishedShifu] = (
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

    def reload(self, app: Flask, reload_generated_block_bid: str):
        with app.app_context():
            generated_block: LearnGeneratedBlock = LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.generated_block_bid == reload_generated_block_bid,
            ).first()
            current_attend = self._get_current_attend(generated_block.outline_item_bid)
            self._can_continue = False
            if generated_block:
                if self._input_type != "ask":
                    app.logger.info(
                        f"reload generated_block: {generated_block.id},block_position: {generated_block.position}"
                    )
                    updated_blocks = LearnGeneratedBlock.query.filter(
                        LearnGeneratedBlock.progress_record_bid
                        == generated_block.progress_record_bid,
                        LearnGeneratedBlock.outline_item_bid
                        == generated_block.outline_item_bid,
                        LearnGeneratedBlock.user_bid == self._user_info.user_id,
                        LearnGeneratedBlock.id >= generated_block.id,
                        LearnGeneratedBlock.position >= generated_block.position,
                    ).all()
                    for updated_block in updated_blocks:
                        app.logger.info(
                            f"updated_block: {updated_block.id}, {updated_block.position}"
                        )
                        updated_block.status = 0

                    current_attend.block_position = generated_block.position
                    current_attend.status = LEARN_STATUS_IN_PROGRESS
                    db.session.commit()
                else:
                    self._last_position = generated_block.position
        with app.app_context():
            yield from self.run(app)
            db.session.commit()
        return
