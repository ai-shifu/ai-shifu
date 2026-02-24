from markdown_flow import (
    InteractionParser,
)
from collections import defaultdict
from flask import Flask, request
import base64
import time
import logging
from dataclasses import replace
import uuid
from flaskr.service.learn.learn_dtos import (
    LearnShifuInfoDTO,
    LearnOutlineItemInfoDTO,
    LearnRecordDTO,
    LearnStatus,
    GeneratedBlockDTO,
    BlockType,
    LikeStatus,
    LearnOutlineItemsWithBannerInfoDTO,
    LearnBannerInfoDTO,
    OutlineType,
    GeneratedInfoDTO,
    RunMarkdownFlowDTO,
    GeneratedType,
    AudioSegmentDTO,
    AudioCompleteDTO,
)
from flaskr.service.shifu.models import (
    DraftShifu,
    PublishedShifu,
    DraftOutlineItem,
    PublishedOutlineItem,
    LogDraftStruct,
    LogPublishedStruct,
)
from flaskr.service.learn.models import LearnProgressRecord, LearnGeneratedBlock
from flaskr.service.tts.models import LearnGeneratedAudio, AUDIO_STATUS_COMPLETED
from flaskr.service.metering import UsageContext, record_tts_usage
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.tts.pipeline import (
    synthesize_long_text_to_oss,
    split_text_for_tts,
)
from flaskr.api.tts import (
    get_default_audio_settings,
    get_default_voice_settings,
    synthesize_text,
    is_tts_configured,
)
from flaskr.service.tts import preprocess_for_tts
from flaskr.service.tts.audio_utils import (
    concat_audio_best_effort,
    get_audio_duration_ms,
)
from flaskr.service.tts.tts_handler import upload_audio_to_oss
from flaskr.service.tts.validation import validate_tts_settings_strict
from flaskr.service.common import raise_error, raise_error_with_args
from flaskr.service.shifu.utils import get_shifu_res_url
from flaskr.service.shifu.shifu_history_manager import HistoryItem
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.service.order.models import Order, BannerInfo
from flaskr.i18n import _
from flaskr.service.order.consts import (
    ORDER_STATUS_SUCCESS,
    LEARN_STATUS_LOCKED,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_RESET,
)
import queue
from flaskr.dao import db
from flaskr.service.shifu.consts import (
    BLOCK_TYPE_MDASK_VALUE,
    BLOCK_TYPE_MDCONTENT_VALUE,
    BLOCK_TYPE_MDINTERACTION_VALUE,
    BLOCK_TYPE_MDERRORMESSAGE_VALUE,
    BLOCK_TYPE_MDANSWER_VALUE,
    BLOCK_TYPE_CONTENT_VALUE,
    BLOCK_TYPE_BUTTON_VALUE,
    BLOCK_TYPE_INPUT_VALUE,
    BLOCK_TYPE_OPTIONS_VALUE,
    BLOCK_TYPE_GOTO_VALUE,
    BLOCK_TYPE_PAYMENT_VALUE,
    BLOCK_TYPE_LOGIN_VALUE,
    BLOCK_TYPE_BREAK_VALUE,
    BLOCK_TYPE_PHONE_VALUE,
    BLOCK_TYPE_CHECKCODE_VALUE,
)
from flaskr.service.learn.const import ROLE_TEACHER, CONTEXT_INTERACTION_NEXT
from flaskr.service.shifu.consts import (
    UNIT_TYPE_VALUE_TRIAL,
    UNIT_TYPE_VALUE_NORMAL,
    UNIT_TYPE_VALUE_GUEST,
)
from flaskr.util import generate_id

STATUS_MAP = {
    LEARN_STATUS_LOCKED: LearnStatus.LOCKED,
    LEARN_STATUS_NOT_STARTED: LearnStatus.NOT_STARTED,
    LEARN_STATUS_IN_PROGRESS: LearnStatus.IN_PROGRESS,
    LEARN_STATUS_COMPLETED: LearnStatus.COMPLETED,
}

logger = logging.getLogger(__name__)


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


def get_shifu_info(app: Flask, shifu_bid: str, preview_mode: bool) -> LearnShifuInfoDTO:
    with app.app_context():
        model = DraftShifu if preview_mode else PublishedShifu
        shifu = (
            model.query.filter(model.shifu_bid == shifu_bid, model.deleted == 0)
            .order_by(model.id.desc())
            .first()
        )
        if not shifu:
            raise_error("server.shifu.shifuNotFound")
        published_shifu = None
        if preview_mode:
            published_shifu = (
                PublishedShifu.query.filter(
                    PublishedShifu.shifu_bid == shifu_bid,
                    PublishedShifu.deleted == 0,
                )
                .order_by(PublishedShifu.id.desc())
                .first()
            )
        else:
            published_shifu = shifu
        tts_enabled = bool(getattr(published_shifu, "tts_enabled", 0))
        return LearnShifuInfoDTO(
            bid=shifu.shifu_bid,
            title=shifu.title,
            description=shifu.description,
            avatar=get_shifu_res_url(shifu.avatar_res_bid),
            price=str(shifu.price),
            keywords=shifu.keywords.split(",") if shifu.keywords else [],
            tts_enabled=tts_enabled,
        )


def get_outline_item_tree(
    app: Flask, shifu_bid: str, user_bid: str, preview_mode: bool
) -> LearnOutlineItemsWithBannerInfoDTO:
    with app.app_context():
        outline_type_map = {
            UNIT_TYPE_VALUE_TRIAL: OutlineType.TRIAL,
            UNIT_TYPE_VALUE_NORMAL: OutlineType.NORMAL,
            UNIT_TYPE_VALUE_GUEST: OutlineType.GUEST,
        }
        is_paid = preview_mode
        if preview_mode:
            outline_item_model = DraftOutlineItem
            struct_model = LogDraftStruct
            shifu_model = DraftShifu
        else:
            outline_item_model = PublishedOutlineItem
            struct_model = LogPublishedStruct
            shifu_model = PublishedShifu
        if not is_paid:
            shifu = (
                shifu_model.query.filter(
                    shifu_model.shifu_bid == shifu_bid, shifu_model.deleted == 0
                )
                .order_by(shifu_model.id.desc())
                .first()
            )
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
            if not buy_record:
                is_paid = False
            else:
                is_paid = True
        struct = (
            struct_model.query.filter(
                struct_model.shifu_bid == shifu_bid, struct_model.deleted == 0
            )
            .order_by(struct_model.id.desc())
            .first()
        )
        if not struct:
            raise_error("server.shifu.shifuStructNotFound")
        struct = HistoryItem.from_json(struct.struct)
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
        outline_items_ids = [i.id for i in outline_items]
        outline_items_bids = [i.bid for i in outline_items]
        outline_items_dbs = outline_item_model.query.filter(
            outline_item_model.id.in_(outline_items_ids),
            outline_item_model.deleted == 0,
        ).all()
        progress_records = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid.in_(outline_items_bids),
            LearnProgressRecord.status != LEARN_STATUS_RESET,
            LearnProgressRecord.deleted == 0,
        ).all()
        progress_records_map: dict[str, LearnProgressRecord] = {
            i.outline_item_bid: i for i in progress_records
        }

        def build_outline_item_tree(item: HistoryItem):
            outline_item: DraftOutlineItem | PublishedOutlineItem = next(
                (i for i in outline_items_dbs if i.id == item.id), None
            )
            if not outline_item or outline_item.hidden == 1:
                return None
            progress_record = progress_records_map.get(
                outline_item.outline_item_bid, None
            )
            if not progress_record:
                status = LEARN_STATUS_NOT_STARTED
            else:
                status = progress_record.status
                if status == LEARN_STATUS_LOCKED:
                    status = LEARN_STATUS_NOT_STARTED
            outline_item_info = LearnOutlineItemInfoDTO(
                bid=outline_item.outline_item_bid,
                position=outline_item.position,
                title=outline_item.title,
                status=STATUS_MAP.get(status, LearnStatus.NOT_STARTED),
                type=outline_type_map.get(outline_item.type, OutlineType.NORMAL),
                is_paid=is_paid,
                children=[],
            )
            if item.children:
                for child in item.children:
                    child_info = build_outline_item_tree(child)
                    if child_info:
                        outline_item_info.children.append(child_info)
            return outline_item_info

        outline_items = []
        for i in struct.children:
            outline_item_info = build_outline_item_tree(i)
            if outline_item_info:
                outline_items.append(outline_item_info)
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
            )
        if not is_paid:
            if add_banner:
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
        )


def get_learn_record(
    app: Flask, shifu_bid: str, outline_bid: str, user_bid: str, preview_mode: bool
) -> LearnRecordDTO:
    with app.app_context():
        progress_record = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        ).first()
        if not progress_record:
            return LearnRecordDTO(
                records=[],
                interaction="",
            )
        app.logger.info(f"progress_record: {progress_record.progress_record_bid}")
        generated_blocks: list[LearnGeneratedBlock] = (
            LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.user_bid == user_bid,
                LearnGeneratedBlock.shifu_bid == shifu_bid,
                LearnGeneratedBlock.progress_record_bid
                == progress_record.progress_record_bid,
                LearnGeneratedBlock.outline_item_bid == outline_bid,
                LearnGeneratedBlock.deleted == 0,
                LearnGeneratedBlock.status == 1,
            )
            .order_by(LearnGeneratedBlock.position.asc(), LearnGeneratedBlock.id.asc())
            .all()
        )

        # Get audio URLs for generated blocks (ordered by position for
        # visual-aware audio splitting support)
        generated_block_bids = [b.generated_block_bid for b in generated_blocks]
        audio_records = (
            LearnGeneratedAudio.query.filter(
                LearnGeneratedAudio.generated_block_bid.in_(generated_block_bids),
                LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
                LearnGeneratedAudio.deleted == 0,
            )
            .order_by(LearnGeneratedAudio.position.asc())
            .all()
        )
        # Build per-block list of audio dicts (position-ordered)
        audio_records_map: dict[str, list[dict]] = defaultdict(list)
        for a in audio_records:
            audio_records_map[a.generated_block_bid].append(
                {
                    "audio_url": a.oss_url,
                    "audio_bid": a.audio_bid,
                    "duration_ms": a.duration_ms or 0,
                    "position": a.position,
                }
            )
        # Backward-compatible single-URL map (first positional audio)
        audio_url_map = {
            bid: recs[0]["audio_url"] for bid, recs in audio_records_map.items() if recs
        }

        records: list[GeneratedBlockDTO] = []
        interaction = ""
        BLOCK_TYPE_MAP = {
            BLOCK_TYPE_MDCONTENT_VALUE: BlockType.CONTENT,
            BLOCK_TYPE_MDINTERACTION_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_MDERRORMESSAGE_VALUE: BlockType.ERROR_MESSAGE,
            BLOCK_TYPE_MDASK_VALUE: BlockType.ASK,
            BLOCK_TYPE_MDANSWER_VALUE: BlockType.ANSWER,
            BLOCK_TYPE_CONTENT_VALUE: BlockType.CONTENT,
            BLOCK_TYPE_BUTTON_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_INPUT_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_OPTIONS_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_GOTO_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_PAYMENT_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_LOGIN_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_BREAK_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_PHONE_VALUE: BlockType.INTERACTION,
            BLOCK_TYPE_CHECKCODE_VALUE: BlockType.INTERACTION,
        }
        LIKE_STATUS_MAP = {
            1: LikeStatus.LIKE,
            -1: LikeStatus.DISLIKE,
            0: LikeStatus.NONE,
        }
        for generated_block in generated_blocks:
            block_type = BLOCK_TYPE_MAP.get(generated_block.type, BlockType.CONTENT)
            if block_type == BlockType.ASK and generated_block.role == ROLE_TEACHER:
                block_type = BlockType.ANSWER

            # For interaction blocks, use block_content_conf (already translated during OUTPUT)
            # For other blocks, use generated_content
            if block_type in (
                BlockType.CONTENT,
                BlockType.ERROR_MESSAGE,
                BlockType.ASK,
                BlockType.ANSWER,
            ):
                content = generated_block.generated_content
            else:
                # INTERACTION and other types use block_content_conf
                content = generated_block.block_content_conf

            block_bid = generated_block.generated_block_bid
            record = GeneratedBlockDTO(
                block_bid,
                content,
                LIKE_STATUS_MAP.get(generated_block.liked, LikeStatus.NONE),
                block_type,
                generated_block.generated_content
                if block_type == BlockType.INTERACTION
                else "",
                audio_url=audio_url_map.get(block_bid),
                audio_records=audio_records_map.get(block_bid) or None,
            )
            records.append(record)
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
                        if button.get("value") == "_sys_login":
                            if bool(request.user.mobile):
                                records.remove(last_record)
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
            app.logger.warning(
                "learn record missing shifu struct: shifu_bid=%s", shifu_bid
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
        if (
            progress_record.status == LEARN_STATUS_COMPLETED
            and has_next_outline
            and not has_next_chapter_button
        ):
            button_label = _("server.learn.nextChapterButton")
            fallback_content = f"?[{button_label}//{CONTEXT_INTERACTION_NEXT}]"
            records.append(
                GeneratedBlockDTO(
                    generate_id(app),
                    fallback_content,
                    LikeStatus.NONE,
                    BlockType.INTERACTION,
                    "",
                )
            )
        return LearnRecordDTO(
            records=records,
            interaction=interaction,
        )


def reset_learn_record(
    app: Flask, shifu_bid: str, outline_bid: str, user_bid: str
) -> bool:
    with app.app_context():
        progress_records = LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        ).all()
        for progress_record in progress_records:
            progress_record.status = LEARN_STATUS_RESET

        db.session.commit()
        return True


def handle_reaction(
    app: Flask, shifu_bid: str, user_bid: str, generated_block_bid: str, action: str
) -> bool:
    with app.app_context():
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
        db.session.commit()
        return True


def get_generated_content(
    app: Flask,
    shifu_bid: str,
    generated_block_bid: str,
    user_bid: str,
    preview_mode: bool,
) -> GeneratedInfoDTO:
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


def _resolve_shifu_tts_settings(
    app: Flask,
    *,
    shifu_bid: str,
    preview_mode: bool,
):
    shifu_model = DraftShifu if preview_mode else PublishedShifu
    shifu = (
        shifu_model.query.filter(
            shifu_model.shifu_bid == shifu_bid,
            shifu_model.deleted == 0,
        )
        .order_by(shifu_model.id.desc())
        .first()
    )
    if not shifu:
        raise_error("server.shifu.shifuNotFound")

    if not getattr(shifu, "tts_enabled", False):
        raise_error("server.shifu.ttsNotEnabled")

    provider = (getattr(shifu, "tts_provider", "") or "").strip().lower()
    tts_model = (getattr(shifu, "tts_model", "") or "").strip()
    voice_id = (getattr(shifu, "tts_voice_id", "") or "").strip()
    speed_raw = getattr(shifu, "tts_speed", None)
    pitch_raw = getattr(shifu, "tts_pitch", None)
    emotion = (getattr(shifu, "tts_emotion", "") or "").strip()

    validated = validate_tts_settings_strict(
        provider=provider,
        model=tts_model,
        voice_id=voice_id,
        speed=speed_raw,
        pitch=pitch_raw,
        emotion=emotion,
    )

    voice_settings = get_default_voice_settings(validated.provider)
    voice_settings.voice_id = validated.voice_id
    voice_settings.speed = validated.speed
    voice_settings.pitch = validated.pitch
    voice_settings.emotion = validated.emotion

    audio_settings = get_default_audio_settings(validated.provider)

    return validated.provider, validated.model, voice_settings, audio_settings


def _yield_tts_segments(
    *,
    text: str,
    provider: str,
    tts_model: str,
    voice_settings,
    audio_settings,
):
    provider_name = (provider or "").strip().lower()
    if not provider_name:
        raise ValueError("TTS provider is required")
    if not is_tts_configured(provider_name):
        raise ValueError(f"TTS provider is not configured: {provider_name}")

    segments = split_text_for_tts(text, provider_name=provider_name)
    if not segments:
        raise ValueError("No speakable text after preprocessing")

    safe_audio_settings = replace(audio_settings, format="mp3")
    for index, segment_text in enumerate(segments):
        segment_start = time.monotonic()
        result = synthesize_text(
            text=segment_text,
            voice_settings=voice_settings,
            audio_settings=safe_audio_settings,
            model=(tts_model or "").strip() or None,
            provider_name=provider_name,
        )
        latency_ms = int((time.monotonic() - segment_start) * 1000)
        yield (
            index,
            result.audio_data,
            int(result.duration_ms or 0),
            segment_text,
            int(result.word_count or 0),
            latency_ms,
        )


def stream_generated_block_audio(
    app: Flask,
    *,
    shifu_bid: str,
    generated_block_bid: str,
    user_bid: str,
    preview_mode: bool,
):
    with app.app_context():
        generated_block = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.user_bid == user_bid,
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.generated_block_bid == generated_block_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        ).first()
        if not generated_block:
            raise_error("server.learn.generatedBlockNotFound")

        existing_audios = (
            LearnGeneratedAudio.query.filter(
                LearnGeneratedAudio.generated_block_bid == generated_block_bid,
                LearnGeneratedAudio.user_bid == user_bid,
                LearnGeneratedAudio.shifu_bid == shifu_bid,
                LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
                LearnGeneratedAudio.deleted == 0,
            )
            .order_by(LearnGeneratedAudio.position.asc())
            .all()
        )
        if existing_audios:
            for audio in existing_audios:
                if audio.oss_url:
                    yield RunMarkdownFlowDTO(
                        outline_bid=generated_block.outline_item_bid or "",
                        generated_block_bid=generated_block_bid,
                        type=GeneratedType.AUDIO_COMPLETE,
                        content=AudioCompleteDTO(
                            audio_url=audio.oss_url,
                            audio_bid=audio.audio_bid,
                            duration_ms=audio.duration_ms or 0,
                            position=audio.position,
                        ),
                    )
            return

        provider, tts_model, voice_settings, audio_settings = (
            _resolve_shifu_tts_settings(
                app,
                shifu_bid=shifu_bid,
                preview_mode=preview_mode,
            )
        )

        raw_text = generated_block.generated_content or ""
        cleaned_text = preprocess_for_tts(raw_text)
        if not cleaned_text or len(cleaned_text.strip()) < 2:
            raise_error_with_args(
                "server.common.paramsError",
                param_message="No speakable text available for TTS synthesis",
            )

        audio_bid = uuid.uuid4().hex
        usage_scene = (
            BILL_USAGE_SCENE_PREVIEW if preview_mode else BILL_USAGE_SCENE_PROD
        )
        usage_context = UsageContext(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=generated_block.outline_item_bid or "",
            progress_record_bid=generated_block.progress_record_bid or "",
            generated_block_bid=generated_block_bid,
            audio_bid=audio_bid,
            usage_scene=usage_scene,
        )
        parent_usage_bid = generate_id(app)
        usage_metadata = {
            "voice_id": voice_settings.voice_id or "",
            "speed": voice_settings.speed,
            "pitch": voice_settings.pitch,
            "emotion": voice_settings.emotion,
            "volume": voice_settings.volume,
            "format": audio_settings.format or "mp3",
            "sample_rate": audio_settings.sample_rate or 24000,
        }
        segment_count = 0
        total_word_count = 0
        audio_parts: list[bytes] = []

        try:
            for (
                index,
                audio_data,
                duration_ms,
                segment_text,
                word_count,
                latency_ms,
            ) in _yield_tts_segments(
                text=raw_text,
                provider=provider,
                tts_model=tts_model,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
            ):
                audio_parts.append(audio_data)
                segment_count += 1
                total_word_count += int(word_count or 0)
                segment_length = len(segment_text or "")
                record_tts_usage(
                    app,
                    usage_context,
                    provider=provider,
                    model=tts_model or "",
                    is_stream=True,
                    input=segment_length,
                    output=segment_length,
                    total=segment_length,
                    word_count=int(word_count or 0),
                    duration_ms=int(duration_ms or 0),
                    latency_ms=int(latency_ms or 0),
                    record_level=1,
                    parent_usage_bid=parent_usage_bid,
                    segment_index=index,
                    segment_count=0,
                    extra=usage_metadata,
                )
                base64_audio = base64.b64encode(audio_data).decode("utf-8")
                yield RunMarkdownFlowDTO(
                    outline_bid=generated_block.outline_item_bid or "",
                    generated_block_bid=generated_block_bid,
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        segment_index=index,
                        audio_data=base64_audio,
                        duration_ms=duration_ms,
                        is_final=False,
                    ),
                )

            final_audio = concat_audio_best_effort(audio_parts)
            if not final_audio:
                raise ValueError("No audio data produced")

            duration_ms = get_audio_duration_ms(final_audio, format="mp3")
            oss_url, bucket_name = upload_audio_to_oss(app, final_audio, audio_bid)
            segment_count = len(audio_parts)
            object_key = f"tts-audio/{audio_bid}.mp3"

            audio_record = LearnGeneratedAudio(
                audio_bid=audio_bid,
                generated_block_bid=generated_block_bid,
                progress_record_bid=generated_block.progress_record_bid,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
                oss_url=oss_url,
                oss_bucket=bucket_name or "",
                oss_object_key=object_key,
                duration_ms=int(duration_ms or 0),
                file_size=len(final_audio),
                audio_format=audio_settings.format or "mp3",
                sample_rate=audio_settings.sample_rate or 24000,
                voice_id=voice_settings.voice_id or "",
                voice_settings={
                    "speed": voice_settings.speed,
                    "pitch": voice_settings.pitch,
                    "emotion": voice_settings.emotion,
                    "volume": voice_settings.volume,
                },
                model=tts_model or "",
                text_length=len(cleaned_text),
                segment_count=segment_count,
                status=AUDIO_STATUS_COMPLETED,
            )
            db.session.add(audio_record)
            db.session.commit()

            raw_length = len(raw_text or "")
            cleaned_length = len(cleaned_text or "")
            record_tts_usage(
                app,
                usage_context,
                usage_bid=parent_usage_bid,
                provider=provider,
                model=tts_model or "",
                is_stream=True,
                input=raw_length,
                output=cleaned_length,
                total=cleaned_length,
                word_count=total_word_count,
                duration_ms=int(duration_ms or 0),
                latency_ms=0,
                record_level=0,
                parent_usage_bid="",
                segment_index=0,
                segment_count=segment_count,
                extra=usage_metadata,
            )

            yield RunMarkdownFlowDTO(
                outline_bid=generated_block.outline_item_bid or "",
                generated_block_bid=generated_block_bid,
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url=oss_url,
                    audio_bid=audio_bid,
                    duration_ms=int(duration_ms or 0),
                ),
            )
        except ValueError as exc:
            raise_error_with_args("server.common.paramsError", param_message=str(exc))
        except Exception:
            app.logger.error("TTS streaming synthesis failed", exc_info=True)
            raise_error("server.common.unknownError")


def stream_preview_tts_audio(
    app: Flask,
    *,
    shifu_bid: str,
    user_bid: str,
    text: str,
    preview_mode: bool,
):
    with app.app_context():
        _unused_user_bid = user_bid  # reserved for future auditing/logging

        provider, tts_model, voice_settings, audio_settings = (
            _resolve_shifu_tts_settings(
                app,
                shifu_bid=shifu_bid,
                preview_mode=preview_mode,
            )
        )

        cleaned_text = preprocess_for_tts(text or "")
        if not cleaned_text or len(cleaned_text.strip()) < 2:
            raise_error_with_args(
                "server.common.paramsError",
                param_message="No speakable text available for TTS synthesis",
            )

        audio_bid = uuid.uuid4().hex
        usage_scene = (
            BILL_USAGE_SCENE_PREVIEW if preview_mode else BILL_USAGE_SCENE_PROD
        )
        usage_context = UsageContext(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            audio_bid=audio_bid,
            usage_scene=usage_scene,
        )
        parent_usage_bid = generate_id(app)
        usage_metadata = {
            "voice_id": voice_settings.voice_id or "",
            "speed": voice_settings.speed,
            "pitch": voice_settings.pitch,
            "emotion": voice_settings.emotion,
            "volume": voice_settings.volume,
            "format": audio_settings.format or "mp3",
            "sample_rate": audio_settings.sample_rate or 24000,
        }
        segment_count = 0
        total_word_count = 0
        audio_parts: list[bytes] = []

        try:
            for (
                index,
                audio_data,
                duration_ms,
                segment_text,
                word_count,
                latency_ms,
            ) in _yield_tts_segments(
                text=text or "",
                provider=provider,
                tts_model=tts_model,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
            ):
                audio_parts.append(audio_data)
                segment_count += 1
                total_word_count += int(word_count or 0)
                segment_length = len(segment_text or "")
                record_tts_usage(
                    app,
                    usage_context,
                    provider=provider,
                    model=tts_model or "",
                    is_stream=True,
                    input=segment_length,
                    output=segment_length,
                    total=segment_length,
                    word_count=int(word_count or 0),
                    duration_ms=int(duration_ms or 0),
                    latency_ms=int(latency_ms or 0),
                    record_level=1,
                    parent_usage_bid=parent_usage_bid,
                    segment_index=index,
                    segment_count=0,
                    extra=usage_metadata,
                )
                base64_audio = base64.b64encode(audio_data).decode("utf-8")
                yield RunMarkdownFlowDTO(
                    outline_bid="",
                    generated_block_bid="",
                    type=GeneratedType.AUDIO_SEGMENT,
                    content=AudioSegmentDTO(
                        segment_index=index,
                        audio_data=base64_audio,
                        duration_ms=duration_ms,
                        is_final=False,
                    ),
                )

            final_audio = concat_audio_best_effort(audio_parts)
            if not final_audio:
                raise ValueError("No audio data produced")

            duration_ms = get_audio_duration_ms(final_audio, format="mp3")
            oss_url, _bucket_name = upload_audio_to_oss(app, final_audio, audio_bid)

            raw_length = len(text or "")
            cleaned_length = len(cleaned_text or "")
            record_tts_usage(
                app,
                usage_context,
                usage_bid=parent_usage_bid,
                provider=provider,
                model=tts_model or "",
                is_stream=True,
                input=raw_length,
                output=cleaned_length,
                total=cleaned_length,
                word_count=total_word_count,
                duration_ms=int(duration_ms or 0),
                latency_ms=0,
                record_level=0,
                parent_usage_bid="",
                segment_index=0,
                segment_count=segment_count,
                extra=usage_metadata,
            )

            yield RunMarkdownFlowDTO(
                outline_bid="",
                generated_block_bid="",
                type=GeneratedType.AUDIO_COMPLETE,
                content=AudioCompleteDTO(
                    audio_url=oss_url,
                    audio_bid=audio_bid,
                    duration_ms=int(duration_ms or 0),
                ),
            )
        except ValueError as exc:
            raise_error_with_args("server.common.paramsError", param_message=str(exc))
        except Exception:
            app.logger.error("Preview TTS streaming failed", exc_info=True)
            raise_error("server.common.unknownError")


def synthesize_generated_block_audio(
    app: Flask,
    *,
    shifu_bid: str,
    generated_block_bid: str,
    user_bid: str,
    preview_mode: bool,
) -> dict:
    """
    Synthesize audio for a generated content block and persist it for later playback.

    Notes:
    - Intended for the C-end learning UI.
    - Uses Shifu-level TTS settings (provider/model/voice).
    - Uploads the final audio to OSS and stores a record in `learn_generated_audios`.
    """
    with app.app_context():
        generated_block = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.user_bid == user_bid,
            LearnGeneratedBlock.shifu_bid == shifu_bid,
            LearnGeneratedBlock.generated_block_bid == generated_block_bid,
            LearnGeneratedBlock.deleted == 0,
            LearnGeneratedBlock.status == 1,
        ).first()
        if not generated_block:
            raise_error("server.learn.generatedBlockNotFound")

        existing_audios = (
            LearnGeneratedAudio.query.filter(
                LearnGeneratedAudio.generated_block_bid == generated_block_bid,
                LearnGeneratedAudio.user_bid == user_bid,
                LearnGeneratedAudio.shifu_bid == shifu_bid,
                LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
                LearnGeneratedAudio.deleted == 0,
            )
            .order_by(LearnGeneratedAudio.position.asc())
            .all()
        )
        if existing_audios:
            first = existing_audios[0]
            result = {
                "audio_url": first.oss_url,
                "audio_bid": first.audio_bid,
                "duration_ms": first.duration_ms or 0,
            }
            if len(existing_audios) > 1:
                result["audio_records"] = [
                    {
                        "audio_url": a.oss_url,
                        "audio_bid": a.audio_bid,
                        "duration_ms": a.duration_ms or 0,
                        "position": a.position,
                    }
                    for a in existing_audios
                    if a.oss_url
                ]
            return result

        provider, tts_model, voice_settings, audio_settings = (
            _resolve_shifu_tts_settings(
                app,
                shifu_bid=shifu_bid,
                preview_mode=preview_mode,
            )
        )

        raw_text = generated_block.generated_content or ""
        cleaned_text = preprocess_for_tts(raw_text)
        if not cleaned_text or len(cleaned_text.strip()) < 2:
            raise_error_with_args(
                "server.common.paramsError",
                param_message="No speakable text available for TTS synthesis",
            )

        audio_bid = uuid.uuid4().hex
        usage_scene = (
            BILL_USAGE_SCENE_PREVIEW if preview_mode else BILL_USAGE_SCENE_PROD
        )
        usage_context = UsageContext(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=generated_block.outline_item_bid or "",
            progress_record_bid=generated_block.progress_record_bid or "",
            generated_block_bid=generated_block_bid,
            audio_bid=audio_bid,
            usage_scene=usage_scene,
        )
        parent_usage_bid = generate_id(app)
        try:
            result = synthesize_long_text_to_oss(
                app,
                text=raw_text,
                provider_name=provider,
                model=tts_model,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                audio_bid=audio_bid,
                usage_context=usage_context,
                parent_usage_bid=parent_usage_bid,
            )
        except ValueError as exc:
            raise_error_with_args("server.common.paramsError", param_message=str(exc))
        except Exception:
            app.logger.error("TTS synthesis failed", exc_info=True)
            raise_error("server.common.unknownError")

        audio_record = LearnGeneratedAudio(
            audio_bid=audio_bid,
            generated_block_bid=generated_block_bid,
            progress_record_bid=generated_block.progress_record_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            oss_url=result.audio_url,
            oss_bucket="",
            oss_object_key=f"tts-audio/{audio_bid}.mp3",
            duration_ms=int(result.duration_ms or 0),
            file_size=0,
            audio_format="mp3",
            sample_rate=24000,
            voice_id=voice_settings.voice_id or "",
            voice_settings={
                "speed": voice_settings.speed,
                "pitch": voice_settings.pitch,
                "emotion": voice_settings.emotion,
                "volume": voice_settings.volume,
            },
            model=tts_model or "",
            text_length=len(cleaned_text),
            segment_count=int(result.segment_count or 0),
            status=AUDIO_STATUS_COMPLETED,
        )
        db.session.add(audio_record)
        db.session.commit()

        return {
            "audio_url": result.audio_url,
            "audio_bid": audio_bid,
            "duration_ms": int(result.duration_ms or 0),
        }


def synthesize_preview_tts_audio(
    app: Flask,
    *,
    shifu_bid: str,
    user_bid: str,
    text: str,
    preview_mode: bool,
) -> dict:
    """
    Synthesize audio for an arbitrary text without persisting any database record.

    Notes:
    - Intended for the editor preview.
    - Uses Shifu-level TTS settings (provider/model/voice).
    - Uploads the final audio to OSS for browser playback, but does not write to DB.
    """
    with app.app_context():
        _unused_user_bid = user_bid  # reserved for future auditing/logging

        provider, tts_model, voice_settings, audio_settings = (
            _resolve_shifu_tts_settings(
                app,
                shifu_bid=shifu_bid,
                preview_mode=preview_mode,
            )
        )

        cleaned_text = preprocess_for_tts(text or "")
        if not cleaned_text or len(cleaned_text.strip()) < 2:
            raise_error_with_args(
                "server.common.paramsError",
                param_message="No speakable text available for TTS synthesis",
            )

        audio_bid = uuid.uuid4().hex
        usage_scene = (
            BILL_USAGE_SCENE_PREVIEW if preview_mode else BILL_USAGE_SCENE_PROD
        )
        usage_context = UsageContext(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            audio_bid=audio_bid,
            usage_scene=usage_scene,
        )
        parent_usage_bid = generate_id(app)
        try:
            result = synthesize_long_text_to_oss(
                app,
                text=text or "",
                provider_name=provider,
                model=tts_model,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                audio_bid=audio_bid,
                usage_context=usage_context,
                parent_usage_bid=parent_usage_bid,
            )
        except ValueError as exc:
            raise_error_with_args("server.common.paramsError", param_message=str(exc))
        except Exception:
            app.logger.error("Preview TTS synthesis failed", exc_info=True)
            raise_error("server.common.unknownError")

        return {
            "audio_url": result.audio_url,
            "audio_bid": audio_bid,
            "duration_ms": int(result.duration_ms or 0),
        }
