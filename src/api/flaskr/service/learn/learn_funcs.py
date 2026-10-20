"""Load and update learning records, reactions, and TTS output."""

import json
import logging
import queue
from collections.abc import Callable
from dataclasses import dataclass

from flask import Flask, has_request_context, request
from flaskr.api.llm import is_live_follow_up_model_available
from flaskr.api.llm.model_selection import selection_model
from flaskr.api.tts import (  # noqa: F401  # kept patchable on the pre-split module path
    AudioSettings,
    VoiceSettings,
    get_default_audio_settings,
    get_default_voice_settings,
    get_tts_provider,
    is_tts_configured,
    synthesize_text,
)
from flaskr.dao.uow import app_context_scope, unit_of_work
from flaskr.i18n import _
from flaskr.service.common import (  # noqa: F401  # kept patchable on the pre-split module path
    raise_error,
    raise_error_with_args,
)
from flaskr.service.learn import learn_tts_audio
from flaskr.service.learn.agent.session_store import (
    stage_agent_session_discard,
)
from flaskr.service.learn.const import CONTEXT_INTERACTION_NEXT
from flaskr.service.learn.learn_dtos import (  # noqa: F401  # kept patchable on the pre-split module path
    AudioCompleteDTO,
    AudioSegmentDTO,
    BlockType,
    GeneratedInfoDTO,
    GeneratedType,
    LearnBannerInfoDTO,
    LearnOutlineItemInfoDTO,
    LearnOutlineItemsWithBannerInfoDTO,
    LearnShifuInfoDTO,
    LearnStatus,
    LikeStatus,
    OutlineType,
    RunMarkdownFlowDTO,
)
from flaskr.service.learn.learn_tts_audio import (  # noqa: F401  # kept patchable on the pre-split module path
    _LUA_ACQUIRE_TTS_SYNTH_SLOT,
    _LUA_RELEASE_TTS_SYNTH_SLOT,
    _TTS_SLOT_ACQUIRED,
    _TTS_SLOT_BYPASS,
    _TTS_SLOT_FULL,
    DEFAULT_MAX_PARALLEL_TTS_SYNTH_COUNT,
    TTS_SYNTH_SEM_TTL_SECONDS,
    _audio_record_matches_speakable_text,
    _audio_record_matches_tts_settings,
    _audio_stream_element_type,
    _build_audio_complete_message,
    _build_audio_segment_message,
    _build_tts_done_message,
    _build_tts_usage_context,
    _build_tts_usage_metadata,
    _finalize_tts_stream_audio,
    _float_settings_match,
    _get_max_parallel_tts_synth_count,
    _get_tts_synth_sem_key,
    _has_speakable_tts_segment,
    _record_stream_segment_usage,
    _record_stream_summary_usage,
    _resolve_runtime_tts_voice_id,
    _resolve_shifu_tts_settings,
    _subtitle_cues_from_audio_record,
    _tts_synth_sem_acquire,
    _tts_synth_sem_release,
    _yield_run_tts_audio_events,
    _yield_stream_tts_audio_segments,
    _yield_tts_segments,
    _yield_tts_synthesis,
    _yield_with_tts_error_mapping,
    stream_generated_block_audio,
    stream_preview_tts_audio,
)
from flaskr.service.learn.legacy_record_builder import (
    LegacyGeneratedBlockRecord,
    LegacyLearnRecord,
    build_legacy_record_for_progress,
)
from flaskr.service.learn.lesson_content_updates import load_lesson_content_states
from flaskr.service.learn.lesson_feedback import (
    build_lesson_feedback_interaction_md,
    is_lesson_feedback_interaction,
)
from flaskr.service.learn.listen_element_matching import (  # noqa: F401  # kept patchable on the pre-split module path
    get_speakable_text_elements,
)
from flaskr.service.learn.live_follow_up_config import (
    get_follow_up_interaction_mode,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.learn.split_module_patching import forward_attribute_writes
from flaskr.service.metering import (  # noqa: F401  # kept patchable on the pre-split module path
    UsageContext,
    record_tts_usage,
)
from flaskr.service.metering.consts import (  # noqa: F401  # kept patchable on the pre-split module path
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_LOCKED,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_RESET,
    ORDER_STATUS_SUCCESS,
)
from flaskr.service.order.models import BannerInfo, Order
from flaskr.service.shifu.consts import (
    ASK_MODE_DEFAULT,
    ASK_MODE_DISABLE,
    UNIT_TYPE_VALUE_GUEST,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_TRIAL,
)
from flaskr.service.shifu.dtos import (
    get_demo_course_content_language,
    get_demo_course_title_language,
)
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    LogDraftStruct,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.service.shifu.utils import get_shifu_res_url
from flaskr.service.tts import (  # noqa: F401  # kept patchable on the pre-split module path
    has_speakable_text,
    preprocess_for_tts,
    resolve_tts_billable_chars,
)
from flaskr.service.tts.api import (  # noqa: F401  # kept patchable on the pre-split module path
    TTSRpmQueueTimeoutError,
    create_streaming_tts_processor,
    find_ready_cloned_voice,
    find_tracked_cloned_voice,
    get_clone_provider_spec,
)
from flaskr.service.tts.audio_record_utils import (  # noqa: F401  # kept patchable on the pre-split module path
    build_completed_audio_record,
    save_audio_record,
)
from flaskr.service.tts.audio_utils import (  # noqa: F401  # kept patchable on the pre-split module path
    concat_audio_best_effort,
    get_audio_duration_ms,
)
from flaskr.service.tts.models import (  # noqa: F401  # kept patchable on the pre-split module path
    AUDIO_STATUS_COMPLETED,
    TTS_MINIMAX_CLONE_STATUS_READY,
    LearnGeneratedAudio,
)
from flaskr.service.tts.pipeline import (
    split_text_for_tts,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.service.tts.subtitle_utils import (  # noqa: F401  # kept patchable on the pre-split module path
    append_subtitle_cue,
    normalize_subtitle_cues,
)
from flaskr.service.tts.tts_handler import (
    upload_audio_to_oss,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.service.tts.validation import (
    validate_tts_settings_strict,  # noqa: F401  # kept patchable on the pre-split module path
)
from flaskr.util import generate_id
from markdown_flow import (
    InteractionParser,
)

STATUS_MAP = {
    LEARN_STATUS_LOCKED: LearnStatus.LOCKED,
    LEARN_STATUS_NOT_STARTED: LearnStatus.NOT_STARTED,
    LEARN_STATUS_IN_PROGRESS: LearnStatus.IN_PROGRESS,
    LEARN_STATUS_COMPLETED: LearnStatus.COMPLETED,
}

logger = logging.getLogger(__name__)


def _is_access_gate_interaction(
    content: str | None, *, is_paid: bool, is_logged_in: bool
) -> bool:
    if not content:
        return False
    try:
        parsed = InteractionParser().parse(content)
    except Exception:
        return False
    buttons = parsed.get("buttons") or []
    for button in buttons:
        value = button.get("value")
        if value == "_sys_pay" and not is_paid:
            return True
        if value == "_sys_login" and not is_logged_in:
            return True
    return False


def _find_feedback_interaction_index(
    records: list[LegacyGeneratedBlockRecord],
) -> int:
    for index, record in enumerate(records):
        if (
            record.block_type == BlockType.INTERACTION
            and is_lesson_feedback_interaction(record.content)
        ):
            return index
    return -1


def _insert_record_before_feedback_tail(
    records: list[LegacyGeneratedBlockRecord],
    record: LegacyGeneratedBlockRecord,
) -> None:
    feedback_index = _find_feedback_interaction_index(records)
    if feedback_index < 0:
        records.append(record)
        return
    records.insert(feedback_index, record)


def _move_feedback_interaction_to_tail(
    records: list[LegacyGeneratedBlockRecord],
) -> None:
    feedback_index = _find_feedback_interaction_index(records)
    if feedback_index < 0 or feedback_index == len(records) - 1:
        return
    feedback_record = records.pop(feedback_index)
    records.append(feedback_record)


def _collect_outline_bids(struct: HistoryItem) -> list[str]:
    outline_bids = []
    q = queue.Queue()
    q.put(struct)
    while not q.empty():
        item: HistoryItem = q.get()
        if item.type == "outline":
            outline_bids.append(item.bid)
        if item.children:
            for child in item.children:
                q.put(child)
    return outline_bids


def _has_next_outline_item(
    struct: HistoryItem, outline_bid: str, hidden_map: dict[str, bool]
) -> bool:
    # Check whether a visible outline item exists after the current one.
    path = find_node_with_parents(struct, outline_bid)
    if not path:
        return False
    for idx in range(len(path) - 1, 0, -1):
        current_node = path[idx]
        parent = path[idx - 1]
        try:
            current_index = next(
                i
                for i, child in enumerate(parent.children)
                if child.bid == current_node.bid
            )
        except StopIteration:
            continue
        for sibling in parent.children[current_index + 1 :]:
            if sibling.type != "outline":
                continue
            if hidden_map.get(sibling.bid, True):
                continue
            return True
    return False


def get_shifu_info(
    app: Flask,
    shifu_bid: str,
    preview_mode: bool,
    *,
    viewer_user_bid: str = "",
) -> LearnShifuInfoDTO:
    """Return shifu info."""
    with app.app_context():
        model = DraftShifu if preview_mode else PublishedShifu
        shifu = (
            model.query.filter(model.shifu_bid == shifu_bid, model.deleted == 0)
            .order_by(model.id.desc())
            .first()
        )
        if not shifu:
            raise_error("server.shifu.shifuNotFound")
        tts_enabled = bool(shifu.tts_enabled)
        return LearnShifuInfoDTO(
            bid=shifu.shifu_bid,
            title=shifu.title,
            description=shifu.description,
            avatar=get_shifu_res_url(shifu.avatar_res_bid),
            price=str(shifu.price),
            keywords=shifu.keywords.split(",") if shifu.keywords else [],
            tts_enabled=tts_enabled,
            default_listen_mode_enabled=bool(
                getattr(shifu, "default_listen_mode_enabled", 0)
            ),
            is_owner=bool(viewer_user_bid)
            and str(shifu.created_user_bid or "").strip()
            == str(viewer_user_bid).strip(),
        )


def _is_lesson_outline(item: HistoryItem) -> bool:
    """Legacy block children belong to a lesson; outline children make a chapter."""
    return item.type == "outline" and not any(
        child.type == "outline" for child in item.children
    )


def get_current_lesson_outline(
    *, shifu_bid: str, outline_bid: str, preview_mode: bool
) -> HistoryItem | None:
    """Resolve a leaf's physical row from the same structure used by the directory."""
    struct_model = LogDraftStruct if preview_mode else LogPublishedStruct
    row = (
        struct_model.query.with_entities(struct_model.struct)
        .filter_by(shifu_bid=shifu_bid, deleted=0)
        .order_by(struct_model.id.desc())
        .first()
    )
    if row is None:
        return None
    pending = [HistoryItem.from_json(row.struct)]
    while pending:
        item = pending.pop()
        if item.bid == outline_bid and _is_lesson_outline(item):
            return item
        pending.extend(item.children)
    return None


def get_current_lesson_outline_id(
    *, shifu_bid: str, outline_bid: str, preview_mode: bool
) -> int | None:
    """Return the current physical row for history/reset scope selection."""
    item = get_current_lesson_outline(
        shifu_bid=shifu_bid, outline_bid=outline_bid, preview_mode=preview_mode
    )
    return item.id if item else None


_OUTLINE_TYPE_MAP = {
    UNIT_TYPE_VALUE_TRIAL: OutlineType.TRIAL,
    UNIT_TYPE_VALUE_NORMAL: OutlineType.NORMAL,
    UNIT_TYPE_VALUE_GUEST: OutlineType.GUEST,
}


@dataclass
class _OutlineTreeContext:
    """Everything the recursive outline builder reads for one learner."""

    outline_items_db_map: dict
    progress_records_map: dict
    content_states: dict
    scoped_empty_previews: set
    agent_preview: bool
    is_paid: bool
    resolve_follow_up_mode: Callable[[HistoryItem], str]


def _load_outline_tree_shifu(
    shifu_model: type, *, shifu_bid: str, user_bid: str, is_paid: bool
) -> tuple[object, bool]:
    """Return the latest course row and whether the learner may read paid lessons."""
    shifu = (
        shifu_model.query.filter(
            shifu_model.shifu_bid == shifu_bid, shifu_model.deleted == 0
        )
        .order_by(shifu_model.id.desc())
        .first()
    )
    if not is_paid:
        if not shifu:
            raise_error("server.shifu.shifuNotFound")
        buy_record = (
            Order.query.filter(
                Order.user_bid == user_bid,
                Order.shifu_bid == shifu_bid,
                Order.status == ORDER_STATUS_SUCCESS,
            )
            .order_by(Order.id.desc())
            .first()
        )
        is_paid = bool(buy_record)
    return shifu, is_paid


def _load_outline_tree_struct(struct_model: type, shifu_bid: str) -> HistoryItem:
    struct = (
        struct_model.query.filter(
            struct_model.shifu_bid == shifu_bid, struct_model.deleted == 0
        )
        .order_by(struct_model.id.desc())
        .first()
    )
    if not struct:
        raise_error("server.shifu.shifuStructNotFound")
    return HistoryItem.from_json(struct.struct)


def _collect_outline_nodes(struct: HistoryItem) -> list[HistoryItem]:
    """Return every outline node in breadth-first order."""
    outline_items: list[HistoryItem] = []
    q = queue.Queue()
    q.put(struct)
    while not q.empty():
        item: HistoryItem = q.get()
        if item.type == "outline":
            outline_items.append(item)
        if item.children:
            for child in item.children:
                q.put(child)
    return outline_items


def _follow_up_mode_resolver(
    struct: HistoryItem, outline_items_db_map: dict, shifu: object
) -> Callable[[HistoryItem], str]:
    """Build the per-node follow-up mode lookup, nearest configured outline first."""
    course_follow_up_model = selection_model(shifu, follow_up=True) if shifu else ""
    course_ask_mode = getattr(shifu, "ask_enabled_status", ASK_MODE_DEFAULT)

    def resolve_follow_up_mode(item: HistoryItem) -> str:
        effective_model = course_follow_up_model
        effective_ask_mode = course_ask_mode
        path = find_node_with_parents(struct, item.bid) or []
        for path_item in reversed(path):
            if path_item.type != "outline":
                continue
            configured_item = outline_items_db_map.get(path_item.id)
            if not configured_item:
                continue
            if configured_item.ask_enabled_status != ASK_MODE_DEFAULT:
                effective_ask_mode = configured_item.ask_enabled_status
                break
        if effective_ask_mode == ASK_MODE_DISABLE:
            return "disabled"
        interaction_mode = get_follow_up_interaction_mode(effective_model)
        if interaction_mode == "live_voice" and not is_live_follow_up_model_available(
            effective_model
        ):
            return "disabled"
        return interaction_mode

    return resolve_follow_up_mode


def _latest_progress_records(
    *, user_bid: str, shifu_bid: str, progress_outline_bids: list[str]
) -> dict[str, LearnProgressRecord]:
    """Return the newest non-reset progress record per outline item."""
    progress_records = (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid.in_(progress_outline_bids),
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.deleted == 0,
        ).all()
        if progress_outline_bids
        else []
    )
    progress_records_map: dict[str, LearnProgressRecord] = {}
    for progress_record in progress_records:
        current_status_record = progress_records_map.get(
            progress_record.outline_item_bid
        )
        if (
            current_status_record is None
            or progress_record.id > current_status_record.id
        ):
            progress_records_map[progress_record.outline_item_bid] = progress_record
    return progress_records_map


def _outline_tree_context(
    *,
    shifu_bid: str,
    user_bid: str,
    preview_mode: bool,
    is_paid: bool,
    shifu: object,
    struct: HistoryItem,
    outline_items: list[HistoryItem],
    outline_items_db_map: dict,
) -> _OutlineTreeContext:
    """Resolve progress, 2.0 preview isolation, and content states for the tree."""
    outline_items_bids = [i.bid for i in outline_items]
    resolve_follow_up_mode = _follow_up_mode_resolver(
        struct, outline_items_db_map, shifu
    )

    from flaskr.service.learn.agent.preview_history import (
        outlines_with_agent_history,
    )
    from flaskr.service.learn.agent.routing import uses_agent_engine

    agent_enabled = uses_agent_engine(shifu_bid)
    agent_preview = preview_mode and agent_enabled
    candidate_outline_ids = {
        item.bid: item.id
        for item in outline_items
        if _is_lesson_outline(item)
        and item.id in outline_items_db_map
        and outline_items_db_map[item.id].shifu_bid == shifu_bid
        and outline_items_db_map[item.id].outline_item_bid == item.bid
        and not outline_items_db_map[item.id].hidden
    }
    # A cleared 2.0 draft must stay isolated even after its session is reset.
    # Truly scriptless 1.0 lessons retain their existing history behavior.
    scoped_empty_previews = (
        outlines_with_agent_history(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bids=[
                bid
                for bid, row_id in candidate_outline_ids.items()
                if not (outline_items_db_map[row_id].content or "").strip()
            ],
        )
        if agent_preview
        else set()
    )
    progress_outline_bids = (
        [
            item.bid
            for item in outline_items
            if item.id in outline_items_db_map
            and not (outline_items_db_map[item.id].content or "").strip()
            and item.bid not in scoped_empty_previews
        ]
        if agent_preview
        else outline_items_bids
    )
    progress_records_map = _latest_progress_records(
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        progress_outline_bids=progress_outline_bids,
    )

    eligible_outline_ids = {
        bid: row_id
        for bid, row_id in candidate_outline_ids.items()
        if agent_preview
        or (
            bid in progress_records_map
            and progress_records_map[bid].status
            in (LEARN_STATUS_IN_PROGRESS, LEARN_STATUS_COMPLETED)
        )
    }
    content_states = (
        load_lesson_content_states(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            preview_mode=preview_mode,
            outline_revisions={
                item.bid: item.content_revision
                for item in outline_items
                if item.bid in eligible_outline_ids
            },
        )
        if agent_enabled
        else {}
    )
    return _OutlineTreeContext(
        outline_items_db_map=outline_items_db_map,
        progress_records_map=progress_records_map,
        content_states=content_states,
        scoped_empty_previews=scoped_empty_previews,
        agent_preview=agent_preview,
        is_paid=is_paid,
        resolve_follow_up_mode=resolve_follow_up_mode,
    )


def _build_outline_item_tree(
    item: HistoryItem, ctx: _OutlineTreeContext
) -> LearnOutlineItemInfoDTO | None:
    if item.type != "outline":
        return None
    outline_item: DraftOutlineItem | PublishedOutlineItem = (
        ctx.outline_items_db_map.get(item.id)
    )
    if not outline_item or outline_item.hidden == 1:
        return None
    progress_record = ctx.progress_records_map.get(outline_item.outline_item_bid)
    if not progress_record:
        status = LEARN_STATUS_NOT_STARTED
    else:
        status = progress_record.status
        if status == LEARN_STATUS_LOCKED:
            status = LEARN_STATUS_NOT_STARTED
    content_state = ctx.content_states.get(outline_item.outline_item_bid)
    if ctx.agent_preview and (
        (outline_item.content or "").strip()
        or outline_item.outline_item_bid in ctx.scoped_empty_previews
    ):
        status = LEARN_STATUS_NOT_STARTED
        if content_state is not None and content_state.started:
            status = (
                LEARN_STATUS_COMPLETED
                if content_state.finished
                else LEARN_STATUS_IN_PROGRESS
            )
    is_lesson_node = _is_lesson_outline(item)
    has_content_update_for_current_user = bool(
        is_lesson_node and content_state and content_state.has_content_update
    )
    outline_item_info = LearnOutlineItemInfoDTO(
        bid=outline_item.outline_item_bid,
        position=outline_item.position,
        title=outline_item.title,
        status=STATUS_MAP.get(status, LearnStatus.NOT_STARTED),
        type=_OUTLINE_TYPE_MAP.get(outline_item.type, OutlineType.NORMAL),
        is_paid=ctx.is_paid,
        has_content_update_for_current_user=has_content_update_for_current_user,
        follow_up_mode=ctx.resolve_follow_up_mode(item),
        children=[],
    )
    if item.children:
        for child in item.children:
            child_info = _build_outline_item_tree(child, ctx)
            if child_info:
                outline_item_info.children.append(child_info)
    return outline_item_info


def _outline_tree_response(
    *,
    shifu_bid: str,
    is_paid: bool,
    outline_items: list[LearnOutlineItemInfoDTO],
) -> LearnOutlineItemsWithBannerInfoDTO:
    """Wrap the outline tree with the course's banner, when one applies."""
    banner_info_dto = None

    banner_info = BannerInfo.query.filter(
        BannerInfo.course_id == shifu_bid,
        BannerInfo.deleted == 0,
    ).first()
    add_banner = banner_info and banner_info.show_banner == 1
    add_lesson_banner = banner_info and banner_info.show_lesson_banner == 1

    if not add_banner and not add_lesson_banner:
        return LearnOutlineItemsWithBannerInfoDTO(
            banner_info=banner_info_dto,
            outline_items=outline_items,
            title_language=get_demo_course_title_language(shifu_bid),
            content_language=get_demo_course_content_language(shifu_bid),
        )
    if not is_paid and add_banner:
        banner_info_dto = LearnBannerInfoDTO(
            title=_("server.banner.bannerTitle"),
            pop_up_title=_("server.banner.bannerPopUpTitle"),
            pop_up_content=_("server.banner.bannerPopUpContent"),
            pop_up_confirm_text=_("server.banner.bannerPopUpConfirmText"),
            pop_up_cancel_text=_("server.banner.bannerPopUpCancelText"),
        )
    return LearnOutlineItemsWithBannerInfoDTO(
        banner_info=banner_info_dto,
        outline_items=outline_items,
        title_language=get_demo_course_title_language(shifu_bid),
        content_language=get_demo_course_content_language(shifu_bid),
    )


def get_outline_item_tree(
    app: Flask, shifu_bid: str, user_bid: str, preview_mode: bool
) -> LearnOutlineItemsWithBannerInfoDTO:
    """Return outline item tree."""
    with app.app_context():
        is_paid = preview_mode
        if preview_mode:
            outline_item_model = DraftOutlineItem
            struct_model = LogDraftStruct
            shifu_model = DraftShifu
        else:
            outline_item_model = PublishedOutlineItem
            struct_model = LogPublishedStruct
            shifu_model = PublishedShifu
        shifu, is_paid = _load_outline_tree_shifu(
            shifu_model, shifu_bid=shifu_bid, user_bid=user_bid, is_paid=is_paid
        )
        struct = _load_outline_tree_struct(struct_model, shifu_bid)
        outline_items = _collect_outline_nodes(struct)
        outline_items_ids = [i.id for i in outline_items]
        outline_items_dbs = outline_item_model.query.filter(
            outline_item_model.id.in_(outline_items_ids),
            outline_item_model.deleted == 0,
        ).all()
        outline_items_db_map = {item.id: item for item in outline_items_dbs}
        ctx = _outline_tree_context(
            shifu_bid=shifu_bid,
            user_bid=user_bid,
            preview_mode=preview_mode,
            is_paid=is_paid,
            shifu=shifu,
            struct=struct,
            outline_items=outline_items,
            outline_items_db_map=outline_items_db_map,
        )

        tree_items = []
        for i in struct.children:
            outline_item_info = _build_outline_item_tree(i, ctx)
            if outline_item_info:
                tree_items.append(outline_item_info)
        return _outline_tree_response(
            shifu_bid=shifu_bid, is_paid=is_paid, outline_items=tree_items
        )


def _drop_tail_login_interaction_for_logged_in_user(
    records: list[LegacyGeneratedBlockRecord],
) -> None:
    """Remove a trailing login interaction once the learner has a mobile."""
    if len(records) > 0:
        last_record = records[-1]
        if last_record.block_type == BlockType.INTERACTION:
            interaction_parser = InteractionParser()
            parsed_interaction = interaction_parser.parse(last_record.content)
            if (
                parsed_interaction.get("buttons")
                and len(parsed_interaction.get("buttons")) > 0
            ):
                for button in parsed_interaction.get("buttons"):
                    if button.get("value") == "_sys_pay":
                        pass
                    if button.get("value") == "_sys_login" and bool(
                        request.user.mobile
                    ):
                        records.remove(last_record)


def _learn_record_has_next_outline(
    app: Flask,
    *,
    shifu_bid: str,
    outline_bid: str,
    preview_mode: bool,
) -> bool:
    """Return whether a visible outline item follows ``outline_bid``."""
    struct_model = LogDraftStruct if preview_mode else LogPublishedStruct
    outline_item_model = DraftOutlineItem if preview_mode else PublishedOutlineItem
    has_next_outline = False
    struct_info = (
        struct_model.query.filter(
            struct_model.shifu_bid == shifu_bid, struct_model.deleted == 0
        )
        .order_by(struct_model.id.desc())
        .first()
    )
    if struct_info:
        struct = HistoryItem.from_json(struct_info.struct)
        outline_bids = _collect_outline_bids(struct)
        if outline_bids:
            outline_items = outline_item_model.query.filter(
                outline_item_model.outline_item_bid.in_(outline_bids),
                outline_item_model.deleted == 0,
            ).all()
            outline_hidden_map = {
                item.outline_item_bid: bool(item.hidden) for item in outline_items
            }
            has_next_outline = _has_next_outline_item(
                struct, outline_bid, outline_hidden_map
            )
    else:
        app.logger.warning("learn record missing shifu struct: shifu_bid=%s", shifu_bid)
    return has_next_outline


def _lesson_feedback_record(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
) -> LegacyGeneratedBlockRecord:
    """Build the lesson feedback interaction, prefilled with saved feedback."""
    saved_feedback = (
        LearnLessonFeedback.query.filter(
            LearnLessonFeedback.user_bid == user_bid,
            LearnLessonFeedback.shifu_bid == shifu_bid,
            LearnLessonFeedback.outline_item_bid == outline_bid,
            LearnLessonFeedback.deleted == 0,
        )
        .order_by(LearnLessonFeedback.id.desc())
        .first()
    )
    feedback_generated_content = ""
    if saved_feedback and 1 <= int(saved_feedback.score or 0) <= 5:
        feedback_generated_content = json.dumps(
            {
                "score": int(saved_feedback.score),
                "comment": saved_feedback.comment or "",
            },
            ensure_ascii=False,
        )
    feedback_content = build_lesson_feedback_interaction_md()
    return LegacyGeneratedBlockRecord(
        generated_block_bid=generate_id(app),
        content=feedback_content,
        like_status=LikeStatus.NONE,
        block_type=BlockType.INTERACTION,
        user_input=feedback_generated_content,
    )


def get_learn_record(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    preview_mode: bool,
    *,
    progress_record_bid: str | None = None,
) -> LegacyLearnRecord:
    """Rebuild the learner's legacy record from persisted progress."""
    with app.app_context():
        is_paid = preview_mode
        if not is_paid:
            buy_record = (
                Order.query.filter(
                    Order.user_bid == user_bid,
                    Order.shifu_bid == shifu_bid,
                    Order.status == ORDER_STATUS_SUCCESS,
                )
                .order_by(Order.id.desc())
                .first()
            )
            is_paid = bool(buy_record)

        progress_query = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        if progress_record_bid is not None:
            progress_query = progress_query.filter(
                LearnProgressRecord.progress_record_bid == progress_record_bid
            )
        progress_record = progress_query.first()
        if not progress_record:
            return LegacyLearnRecord(
                records=[],
            )
        app.logger.info("progress_record: %s", progress_record.progress_record_bid)
        records = build_legacy_record_for_progress(
            progress_record,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            include_like_status=True,
            dedupe_blocks_by_bid=False,
            dedupe_audio_by_block_position=False,
            skip_empty_content=False,
        ).records
        _drop_tail_login_interaction_for_logged_in_user(records)
        has_next_outline = _learn_record_has_next_outline(
            app,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            preview_mode=preview_mode,
        )
        if not has_next_outline:
            records = [
                record
                for record in records
                if not (
                    record.block_type == BlockType.INTERACTION
                    and CONTEXT_INTERACTION_NEXT in record.content
                )
            ]
        has_next_chapter_button = any(
            record.block_type == BlockType.INTERACTION
            and CONTEXT_INTERACTION_NEXT in record.content
            for record in records
        )
        has_feedback_interaction = any(
            record.block_type == BlockType.INTERACTION
            and is_lesson_feedback_interaction(record.content)
            for record in records
        )
        has_tail_access_gate = bool(
            records
            and records[-1].block_type == BlockType.INTERACTION
            and _is_access_gate_interaction(
                records[-1].content,
                is_paid=is_paid,
                is_logged_in=bool(
                    getattr(getattr(request, "user", None), "mobile", None)
                    or getattr(getattr(request, "user", None), "email", None)
                )
                if has_request_context()
                else False,
            )
        )
        if (
            progress_record.status == LEARN_STATUS_COMPLETED
            and has_next_outline
            and not has_tail_access_gate
            and not has_next_chapter_button
        ):
            button_label = _("server.learn.nextChapterButton")
            fallback_content = f"?[{button_label}//{CONTEXT_INTERACTION_NEXT}]"
            _insert_record_before_feedback_tail(
                records,
                LegacyGeneratedBlockRecord(
                    generated_block_bid=generate_id(app),
                    content=fallback_content,
                    like_status=LikeStatus.NONE,
                    block_type=BlockType.INTERACTION,
                    user_input="",
                ),
            )

        if (
            progress_record.status == LEARN_STATUS_COMPLETED or has_tail_access_gate
        ) and not has_feedback_interaction:
            feedback_record = _lesson_feedback_record(
                app,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                outline_bid=outline_bid,
            )
            records.append(feedback_record)
        _move_feedback_interaction_to_tail(records)
        return LegacyLearnRecord(
            records=records,
        )


def reset_learn_record(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    *,
    preview_mode: bool = False,
) -> bool:
    """Reset learner progress, or only the explicitly selected draft preview."""
    with app_context_scope(app), unit_of_work():
        from flaskr.service.learn.agent.routing import uses_agent_engine

        if preview_mode and uses_agent_engine(shifu_bid):
            from flaskr.service.learn.agent.preview_history import (
                uses_preview_session_history,
            )

            if not DraftOutlineItem.query.filter_by(
                shifu_bid=shifu_bid, outline_item_bid=outline_bid, deleted=0
            ).first():
                return True
            if uses_preview_session_history(
                app, user_bid=user_bid, shifu_bid=shifu_bid, outline_bid=outline_bid
            ):
                stage_agent_session_discard(
                    user_bid=user_bid,
                    shifu_bid=shifu_bid,
                    outline_item_bid=outline_bid,
                    preview_mode=True,
                )
                return True
        progress_records = (
            LearnProgressRecord.query.filter(
                LearnProgressRecord.user_bid == user_bid,
                LearnProgressRecord.shifu_bid == shifu_bid,
                LearnProgressRecord.outline_item_bid == outline_bid,
                LearnProgressRecord.deleted == 0,
                LearnProgressRecord.status != LEARN_STATUS_RESET,
            )
            # Locked, because a 2.0 turn already running claims the same row before it writes.
            # Without this the two interleave: the turn sees a live lesson, this finds no session
            # to discard, and the turn inserts one afterwards -- returning the conversation the
            # learner just cleared. Taking the lock makes one of them go first, either way.
            .with_for_update()
            .all()
        )
        for progress_record in progress_records:
            progress_record.status = LEARN_STATUS_RESET
        # A 2.0 lesson keeps its conversation in its own table, which resetting the progress
        # records does not touch. Left behind, the next run resumes a session that may hold
        # `finished=True` -- it would report the lesson complete immediately and never start it
        # again, which also breaks taking a course back off the allowlist as a way out.
        stage_agent_session_discard(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            preview_mode=preview_mode,
        )
        return True


def handle_reaction(
    app: Flask, shifu_bid: str, user_bid: str, generated_block_bid: str, action: str
) -> bool:
    """Persist a learner's reaction to one generated block."""
    with app_context_scope(app), unit_of_work():
        generated_block = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.user_bid == user_bid,
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.generated_block_bid == generated_block_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        ).first()
        if not generated_block:
            raise_error("server.learn.generatedBlockNotFound")
        if action not in ["like", "dislike", "none"]:
            raise_error("server.learn.invalidAction")
        if action == "like":
            generated_block.liked = 1
        if action == "dislike":
            generated_block.liked = -1
        if action == "none":
            generated_block.liked = 0
        return True


def get_generated_content(
    app: Flask,
    shifu_bid: str,
    generated_block_bid: str,
    user_bid: str,
    preview_mode: bool,
) -> GeneratedInfoDTO:
    """Return generated content."""
    with app.app_context():
        generated_block = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.user_bid == user_bid,
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.generated_block_bid == generated_block_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        ).first()
        if not generated_block:
            return GeneratedInfoDTO(
                position=0,
                outline_name="",
                is_trial_lesson=False,
            )
        if preview_mode:
            outline_item = (
                DraftOutlineItem.query.filter(
                    DraftOutlineItem.outline_item_bid
                    == generated_block.outline_item_bid,
                    DraftOutlineItem.deleted == 0,
                )
                .order_by(DraftOutlineItem.position.asc())
                .first()
            )
        else:
            outline_item = (
                PublishedOutlineItem.query.filter(
                    PublishedOutlineItem.outline_item_bid
                    == generated_block.outline_item_bid,
                    PublishedOutlineItem.deleted == 0,
                )
                .order_by(PublishedOutlineItem.position.asc())
                .first()
            )
        outline_title = outline_item.title if outline_item else ""
        is_trial_lesson = (
            outline_item.type == UNIT_TYPE_VALUE_TRIAL if outline_item else False
        )
        return GeneratedInfoDTO(
            position=generated_block.position,
            outline_name=outline_title,
            is_trial_lesson=is_trial_lesson,
        )


def resolve_outline_progression(
    app: Flask, *, shifu_bid: str, outline_bid: str, preview_mode: bool
) -> list:
    """Read the course outline and work out what a finished 2.0 lesson changed in it.

    Here rather than beside the rest of the 2.0 lesson code because reading a course's outline is
    this service's business with the course service, already done a few lines up for the learner's
    own outline. Deciding what the change means is a walk over a tree and lives on its own in
    `agent/outline_progression.py`, which knows nothing about either service.

    The outline comes from the same table the learner's own outline does, so they are advanced
    through the outline they were served rather than a different version of it.
    """
    from flaskr.service.learn.agent.outline_progression import plan_lesson_completion

    struct_model = LogDraftStruct if preview_mode else LogPublishedStruct
    outline_model = DraftOutlineItem if preview_mode else PublishedOutlineItem
    row = (
        struct_model.query.filter(
            struct_model.shifu_bid == shifu_bid, struct_model.deleted == 0
        )
        .order_by(struct_model.id.desc())
        .first()
    )
    if row is None:
        return []
    struct = HistoryItem.from_json(row.struct)
    # By row, not by bid. One bid can have several rows kept at once -- a draft clone carries the
    # bid over, and publishing writes a fresh row per node -- and the structure names the exact
    # row it was built from, so asking by bid can answer from a revision never served.
    bid_of_row: dict[int, str] = {}
    pending = [struct]
    while pending:
        item = pending.pop()
        if item.type == "outline":
            bid_of_row[item.id] = item.bid
        pending.extend(item.children)
    rows = (
        outline_model.query.with_entities(
            outline_model.id, outline_model.hidden, outline_model.title
        )
        .filter(outline_model.id.in_(bid_of_row), outline_model.deleted == 0)
        .all()
    )
    hidden = {bid_of_row[row]: bool(is_hidden) for row, is_hidden, _title in rows}
    titles = {bid_of_row[row]: title or "" for row, _hidden, title in rows}
    app.logger.debug(
        "outline progression: shifu_bid=%s outline_bid=%s items=%d",
        shifu_bid,
        outline_bid,
        len(bid_of_row),
    )
    return plan_lesson_completion(struct, outline_bid, hidden, titles)


# The TTS half of this module lives in learn_tts_audio; forward patches applied
# here (tests and plugins patch names on ``flaskr.service.learn.learn_funcs``)
# so the moved code keeps seeing them.
forward_attribute_writes(__name__, (learn_tts_audio,))
