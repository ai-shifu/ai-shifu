"""Read-side state resolution for the learn /run chain (B6 PR3).

``RunStateResolver`` owns the pure READ half of the runtime state cluster
formerly inlined in ``RunScriptContextV2``: outline-tree traversal, block
cursor / completion resolution, and run-script info lookup. It never writes
through ``db.session`` and never opens a ``unit_of_work()`` — persistence
belongs to ``RunRecorder`` (recorder.py) and event construction to
``RunEventEmitter`` (emitter.py).

PR3 scope notes (mirroring the emitter's PR1 conventions):

- The resolver keeps a back-reference to the context and reads the runtime
  inputs (``_struct``, ``_current_outline_item``, ``_current_attend``,
  ``_outline_model``, ``_user_info``, ``_preview_mode``, ``app``) at call
  time through the named properties below. Tests build contexts via
  ``RunScriptContextV2.__new__`` and assign these attributes afterwards, so
  capturing them at construction would freeze half-initialized values; the
  property layer keeps the dependency surface explicit for the Go port
  while staying safe under lazy creation.
- Cross-method calls are dispatched back through the context wrappers
  (``ctx._is_leaf_outline_item``, ``ctx._get_outline_row_id``, ...) so
  instance-level monkey-patches on the context keep taking effect.
- ``MdflowContextV2``, ``RunScriptInfo`` and
  ``get_outline_item_dto_with_mdflow`` are resolved lazily through the
  ``context_v2`` module namespace: importing them at module load would be a
  circular import (context_v2 imports this module), and tests patch the
  names on ``flaskr.service.learn.context_v2`` directly.
- ``_get_current_attend`` deliberately stays on the context: it creates
  progress-record placeholders (a write through the recorder), so it is not
  a pure read and will be split when the write half moves in a later batch.
"""

import queue
from typing import TYPE_CHECKING, Union

from flaskr.dao import db
from flaskr.service.common import raise_error
from flaskr.service.learn.learn_dtos import LearnStatus, OutlineItemUpdateDTO
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.struct_utils import find_node_with_parents

if TYPE_CHECKING:  # pragma: no cover - import cycle guard, typing only
    from flask import Flask

    from flaskr.service.learn.context_v2 import RunScriptContextV2, RunScriptInfo
    from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto


def _runtime():
    """Resolve the context_v2 module lazily.

    Lazy for two reasons: ``context_v2`` imports this module at load time
    (top-level import here would be circular), and tests patch
    ``flaskr.service.learn.context_v2.get_outline_item_dto_with_mdflow`` /
    ``...MarkdownFlow`` — attribute access at call time sees those patches.
    """
    from flaskr.service.learn import context_v2

    return context_v2


class RunStateResolver:
    """Pure read-side resolution of /run outline and progress state.

    Holds a back-reference to ``RunScriptContextV2`` and reads the runtime
    inputs at call time; performs no DB writes.
    """

    def __init__(self, context: "RunScriptContextV2") -> None:
        self._context = context

    # -- explicit runtime inputs, read from the context at call time --

    @property
    def app(self) -> "Flask":
        return self._context.app

    @property
    def _struct(self) -> HistoryItem:
        return self._context._struct

    @property
    def _preview_mode(self) -> bool:
        return self._context._preview_mode

    @property
    def _outline_model(self):
        return self._context._outline_model

    @property
    def _user_bid(self) -> str:
        return self._context._user_info.user_id

    @property
    def _current_outline_item(self):
        return self._context._current_outline_item

    @property
    def _current_attend(self) -> LearnProgressRecord:
        return self._context._current_attend

    # outline is a leaf when has block item as children
    # outline is a node when has outline item as children
    # outline is a leaf when has no children
    def is_leaf_outline_item(self, outline_item_info: "ShifuOutlineItemDto") -> bool:
        if outline_item_info.children:
            if outline_item_info.children[0].type == "block":
                return True
            if outline_item_info.children[0].type == "outline":
                return False
        if outline_item_info.type == "outline":
            return True
        return False

    def get_current_outline_block_count(self) -> int:
        """
        Determine the completion threshold for the current outline.

        History metadata (`child_count` / block children) can lag behind the
        latest mdflow document. When that happens, relying on the history tree
        alone may prematurely mark the outline as completed before runtime
        reaches a later interaction block.
        """
        ctx = self._context
        if not self._current_outline_item:
            return 0

        history_block_count = max(
            len(self._current_outline_item.children),
            self._current_outline_item.child_count,
        )
        # Dispatch through the context wrapper so instance-level overrides
        # (tests patch these seams) keep taking effect.
        if not ctx._is_leaf_outline_item(self._current_outline_item):
            return history_block_count

        outline_bid = self._current_outline_item.bid
        block_count_cache = getattr(self, "_outline_block_count_cache", None)
        if not isinstance(block_count_cache, dict):
            block_count_cache = {}
            self._outline_block_count_cache = block_count_cache
        if outline_bid in block_count_cache:
            return block_count_cache[outline_bid]

        runtime = _runtime()
        try:
            outline_item_info = runtime.get_outline_item_dto_with_mdflow(
                self.app,
                outline_bid,
                self._preview_mode,
                outline_item_id=int(self._current_outline_item.id or 0),
            )
            block_count = len(
                runtime.MdflowContextV2(
                    document=outline_item_info.mdflow
                ).get_all_blocks()
            )
            block_count_cache[outline_bid] = block_count
            return block_count
        except Exception as exc:
            self.app.logger.warning(
                "Load runtime block count failed for outline %s: %s",
                outline_bid,
                exc,
                exc_info=True,
            )
            return history_block_count

    # get the outline items to start or complete
    def get_next_outline_item(self) -> list[OutlineItemUpdateDTO]:
        ctx = self._context
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
            if ctx._is_leaf_outline_item(outline_item_info):
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

        if (
            self._current_attend.block_position
            >= ctx._get_current_outline_block_count()
        ):
            _mark_sub_node_completed(self._current_outline_item, res)
        if self._current_attend.status == LEARN_STATUS_NOT_STARTED:
            _mark_sub_node_start(self._current_outline_item, res)
        return res

    def has_next_outline_item(
        self, outline_updates: list[OutlineItemUpdateDTO]
    ) -> bool:
        if not outline_updates:
            return False
        current_bid = (
            self._current_outline_item.bid if self._current_outline_item else ""
        )
        return any(
            update.status == LearnStatus.IN_PROGRESS
            and update.outline_bid != current_bid
            for update in outline_updates
        )

    def is_current_outline_completed(
        self, outline_updates: list[OutlineItemUpdateDTO]
    ) -> bool:
        if not outline_updates or not self._current_outline_item:
            return False
        current_bid = self._current_outline_item.bid
        return any(
            update.outline_bid == current_bid and update.status == LearnStatus.COMPLETED
            for update in outline_updates
        )

    def get_outline_struct(self, outline_item_id: str) -> HistoryItem:
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

    def get_outline_row_id(self, outline_item_bid: str) -> Union[int, None]:
        ctx = self._context
        if not outline_item_bid:
            return None
        if (
            self._current_outline_item
            and self._current_outline_item.bid == outline_item_bid
            and getattr(self._current_outline_item, "id", None)
        ):
            return int(self._current_outline_item.id)
        outline_struct = ctx._get_outline_struct(outline_item_bid)
        if outline_struct and getattr(outline_struct, "id", None):
            return int(outline_struct.id)
        return None

    def get_run_script_info(
        self, attend: LearnProgressRecord, is_ask: bool = False
    ) -> "RunScriptInfo":
        ctx = self._context
        runtime = _runtime()
        outline_item_id = attend.outline_item_bid
        outline_row_id = ctx._get_outline_row_id(outline_item_id)
        outline_item_info = runtime.get_outline_item_dto_with_mdflow(
            self.app,
            outline_item_id,
            self._preview_mode,
            outline_item_id=outline_row_id,
        )

        mdflow_context = runtime.MdflowContextV2(document=outline_item_info.mdflow)
        block_list = mdflow_context.get_all_blocks()
        self.app.logger.info(
            f"attend position: {attend.block_position} blocks:{len(block_list)}"
        )
        if attend.block_position >= len(block_list) and not is_ask:
            return None
        return runtime.RunScriptInfo(
            attend=attend,
            outline_bid=outline_item_info.outline_bid,
            block_position=attend.block_position,
            mdflow=outline_item_info.mdflow,
        )

    def get_run_script_info_by_block_id(self, block_id: str) -> "RunScriptInfo":
        ctx = self._context
        runtime = _runtime()
        generate_block: LearnGeneratedBlock = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == block_id,
            LearnGeneratedBlock.deleted == 0,
        ).first()
        if not generate_block:
            raise_error("server.shifu.lessonNotFoundInCourse")
        outline_row_id = ctx._get_outline_row_id(generate_block.outline_item_bid)
        outline_item_info = runtime.get_outline_item_dto_with_mdflow(
            self.app,
            generate_block.outline_item_bid,
            self._preview_mode,
            outline_item_id=outline_row_id,
        )
        attend: LearnProgressRecord = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == self._user_bid,
            LearnProgressRecord.shifu_bid == outline_item_info.shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_item_info.bid,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        ).first()
        return runtime.RunScriptInfo(
            attend=attend,
            outline_bid=outline_item_info.outline_bid,
            block_position=generate_block.position,
            mdflow=outline_item_info.mdflow,
        )
