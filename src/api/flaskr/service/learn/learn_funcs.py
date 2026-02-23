from markdown_flow import (
    InteractionParser,
)
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
    split_text_for_tts,
    build_av_segmentation_contract,
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
from flaskr.service.tts.audio_record_utils import (
    build_completed_audio_record,
    save_audio_record,
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
from flaskr.service.learn.listen_slide_builder import build_listen_slides_for_block
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

        # Get audio records for generated blocks (no joins; compose in Python).
        generated_block_bids = [b.generated_block_bid for b in generated_blocks]
        audios_map: dict[str, list[AudioCompleteDTO]] = {}
        if generated_block_bids:
            audio_records = (
                LearnGeneratedAudio.query.filter(
                    LearnGeneratedAudio.generated_block_bid.in_(generated_block_bids),
                    LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
                    LearnGeneratedAudio.deleted == 0,
                )
                .order_by(
                    LearnGeneratedAudio.generated_block_bid.asc(),
                    LearnGeneratedAudio.position.asc(),
                    LearnGeneratedAudio.id.asc(),
                )
                .all()
            )
            for audio in audio_records:
                position = int(getattr(audio, "position", 0) or 0)
                audios_map.setdefault(audio.generated_block_bid, []).append(
                    AudioCompleteDTO(
                        audio_url=audio.oss_url or "",
                        audio_bid=audio.audio_bid or "",
                        duration_ms=int(audio.duration_ms or 0),
                        position=position,
                    )
                )

        records: list[GeneratedBlockDTO] = []
        slides = []
        next_slide_index = 0
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

            block_audios = audios_map.get(generated_block.generated_block_bid) or []
            av_contract = (
                build_av_segmentation_contract(
                    content or "", generated_block.generated_block_bid
                )
                if block_type == BlockType.CONTENT and (content or "").strip()
                else None
            )

            audio_position_to_slide_id: dict[int, str] = {}
            if av_contract is not None:
                block_slides, audio_position_to_slide_id = (
                    build_listen_slides_for_block(
                        raw_content=content or "",
                        generated_block_bid=generated_block.generated_block_bid,
                        av_contract=av_contract,
                        slide_index_offset=next_slide_index,
                    )
                )
                if block_slides:
                    slides.extend(block_slides)
                    next_slide_index = int(block_slides[-1].slide_index or 0) + 1

            if block_audios and audio_position_to_slide_id:
                enriched_block_audios: list[AudioCompleteDTO] = []
                for audio in block_audios:
                    audio_position = int(getattr(audio, "position", 0) or 0)
                    mapped_slide_id = audio_position_to_slide_id.get(audio_position)
                    if not mapped_slide_id:
                        enriched_block_audios.append(audio)
                        continue
                    enriched_block_audios.append(
                        AudioCompleteDTO(
                            audio_url=audio.audio_url,
                            audio_bid=audio.audio_bid,
                            duration_ms=int(audio.duration_ms or 0),
                            position=audio_position,
                            slide_id=mapped_slide_id,
                            av_contract=getattr(audio, "av_contract", None),
                        )
                    )
                block_audios = enriched_block_audios

            record = GeneratedBlockDTO(
                generated_block.generated_block_bid,
                content,
                LIKE_STATUS_MAP.get(generated_block.liked, LikeStatus.NONE),
                block_type,
                generated_block.generated_content
                if block_type == BlockType.INTERACTION
                else "",
                audio_url=block_audios[0].audio_url if len(block_audios) == 1 else None,
                audios=block_audios or None,
                av_contract=av_contract,
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
            slides=slides or None,
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


def _build_tts_usage_metadata(*, voice_settings, audio_settings) -> dict:
    return {
        "voice_id": voice_settings.voice_id or "",
        "speed": voice_settings.speed,
        "pitch": voice_settings.pitch,
        "emotion": voice_settings.emotion,
        "volume": voice_settings.volume,
        "format": audio_settings.format or "mp3",
        "sample_rate": audio_settings.sample_rate or 24000,
    }


def _build_tts_usage_context(
    *,
    user_bid: str,
    shifu_bid: str,
    audio_bid: str,
    usage_scene: int,
    outline_item_bid: str | None = None,
    progress_record_bid: str | None = None,
    generated_block_bid: str | None = None,
) -> UsageContext:
    kwargs = {
        "user_bid": user_bid,
        "shifu_bid": shifu_bid,
        "audio_bid": audio_bid,
        "usage_scene": usage_scene,
    }
    if outline_item_bid is not None:
        kwargs["outline_item_bid"] = outline_item_bid
    if progress_record_bid is not None:
        kwargs["progress_record_bid"] = progress_record_bid
    if generated_block_bid is not None:
        kwargs["generated_block_bid"] = generated_block_bid
    return UsageContext(**kwargs)


def _finalize_tts_stream_audio(
    app: Flask,
    *,
    audio_parts: list[bytes],
    audio_bid: str,
    audio_settings,
    voice_settings,
    tts_model: str,
    cleaned_text: str,
    segment_count: int,
    persist_audio: bool,
    generated_block_bid: str = "",
    progress_record_bid: str = "",
    user_bid: str = "",
    shifu_bid: str = "",
    position: int | None = None,
) -> tuple[str, int]:
    final_audio = concat_audio_best_effort(audio_parts)
    if not final_audio:
        raise ValueError("No audio data produced")

    duration_ms = int(get_audio_duration_ms(final_audio, format="mp3") or 0)
    oss_url, bucket_name = upload_audio_to_oss(app, final_audio, audio_bid)

    if persist_audio:
        object_key = f"tts-audio/{audio_bid}.mp3"
        audio_record = build_completed_audio_record(
            audio_bid=audio_bid,
            generated_block_bid=generated_block_bid,
            position=int(position or 0),
            progress_record_bid=progress_record_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            oss_url=oss_url,
            oss_bucket=bucket_name or "",
            oss_object_key=object_key,
            duration_ms=duration_ms,
            file_size=len(final_audio),
            audio_format=audio_settings.format or "mp3",
            sample_rate=audio_settings.sample_rate or 24000,
            voice_settings=voice_settings,
            tts_model=tts_model or "",
            text_length=len(cleaned_text or ""),
            segment_count=segment_count,
        )
        save_audio_record(audio_record, commit=True)

    return oss_url, duration_ms


def _yield_with_tts_error_mapping(
    app: Flask,
    *,
    unknown_error_log: str,
    body,
):
    try:
        yield from body()
    except ValueError as exc:
        raise_error_with_args("server.common.paramsError", param_message=str(exc))
    except Exception:
        app.logger.error(unknown_error_log, exc_info=True)
        raise_error("server.common.unknownError")


def _record_stream_segment_usage(
    app: Flask,
    usage_context: UsageContext,
    *,
    provider: str,
    tts_model: str,
    segment_text: str,
    word_count: int,
    duration_ms: int,
    latency_ms: int,
    parent_usage_bid: str,
    segment_index: int,
    usage_metadata: dict,
):
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
        segment_index=segment_index,
        segment_count=0,
        extra=usage_metadata,
    )


def _record_stream_summary_usage(
    app: Flask,
    usage_context: UsageContext,
    *,
    usage_bid: str,
    provider: str,
    tts_model: str,
    raw_text: str,
    cleaned_text: str,
    total_word_count: int,
    duration_ms: int,
    segment_count: int,
    usage_metadata: dict,
):
    raw_length = len(raw_text or "")
    cleaned_length = len(cleaned_text or "")
    record_tts_usage(
        app,
        usage_context,
        usage_bid=usage_bid,
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


def _build_audio_segment_message(
    *,
    outline_bid: str,
    generated_block_bid: str,
    segment_index: int,
    audio_data: bytes,
    duration_ms: int,
    position: int | None = None,
    av_contract: dict | None = None,
) -> RunMarkdownFlowDTO:
    content_kwargs = {
        "segment_index": segment_index,
        "audio_data": base64.b64encode(audio_data).decode("utf-8"),
        "duration_ms": duration_ms,
        "is_final": False,
    }
    if position is not None:
        content_kwargs["position"] = position
    if av_contract is not None:
        content_kwargs["av_contract"] = av_contract

    return RunMarkdownFlowDTO(
        outline_bid=outline_bid or "",
        generated_block_bid=generated_block_bid or "",
        type=GeneratedType.AUDIO_SEGMENT,
        content=AudioSegmentDTO(**content_kwargs),
    )


def _build_audio_complete_message(
    *,
    outline_bid: str,
    generated_block_bid: str,
    audio_url: str,
    audio_bid: str,
    duration_ms: int,
    position: int | None = None,
    av_contract: dict | None = None,
) -> RunMarkdownFlowDTO:
    content_kwargs = {
        "audio_url": audio_url or "",
        "audio_bid": audio_bid or "",
        "duration_ms": int(duration_ms or 0),
    }
    if position is not None:
        content_kwargs["position"] = position
    if av_contract is not None:
        content_kwargs["av_contract"] = av_contract

    return RunMarkdownFlowDTO(
        outline_bid=outline_bid or "",
        generated_block_bid=generated_block_bid or "",
        type=GeneratedType.AUDIO_COMPLETE,
        content=AudioCompleteDTO(**content_kwargs),
    )


def _yield_stream_tts_audio_segments(
    *,
    app: Flask,
    text: str,
    provider: str,
    tts_model: str,
    voice_settings,
    audio_settings,
    usage_context: UsageContext,
    parent_usage_bid: str,
    usage_metadata: dict,
    outline_bid: str,
    generated_block_bid: str,
    audio_parts: list[bytes],
    stats: dict,
    position: int | None = None,
    av_contract: dict | None = None,
):
    for (
        index,
        audio_data,
        duration_ms,
        segment_text,
        word_count,
        latency_ms,
    ) in _yield_tts_segments(
        text=text,
        provider=provider,
        tts_model=tts_model,
        voice_settings=voice_settings,
        audio_settings=audio_settings,
    ):
        audio_parts.append(audio_data)
        stats["segment_count"] = int(stats.get("segment_count", 0)) + 1
        stats["total_word_count"] = int(stats.get("total_word_count", 0)) + int(
            word_count or 0
        )
        _record_stream_segment_usage(
            app,
            usage_context,
            provider=provider,
            tts_model=tts_model,
            segment_text=segment_text,
            word_count=int(word_count or 0),
            duration_ms=int(duration_ms or 0),
            latency_ms=int(latency_ms or 0),
            parent_usage_bid=parent_usage_bid,
            segment_index=index,
            usage_metadata=usage_metadata,
        )
        yield _build_audio_segment_message(
            outline_bid=outline_bid,
            generated_block_bid=generated_block_bid,
            segment_index=index,
            audio_data=audio_data,
            duration_ms=duration_ms,
            position=position,
            av_contract=av_contract,
        )


def stream_generated_block_audio(
    app: Flask,
    *,
    shifu_bid: str,
    generated_block_bid: str,
    user_bid: str,
    preview_mode: bool,
    listen: bool = False,
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

        if not listen:
            existing_audio = (
                LearnGeneratedAudio.query.filter(
                    LearnGeneratedAudio.generated_block_bid == generated_block_bid,
                    LearnGeneratedAudio.user_bid == user_bid,
                    LearnGeneratedAudio.shifu_bid == shifu_bid,
                    LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
                    LearnGeneratedAudio.deleted == 0,
                )
                .order_by(LearnGeneratedAudio.id.desc())
                .first()
            )
            if existing_audio and existing_audio.oss_url:
                yield _build_audio_complete_message(
                    outline_bid=generated_block.outline_item_bid or "",
                    generated_block_bid=generated_block_bid,
                    audio_url=existing_audio.oss_url,
                    audio_bid=existing_audio.audio_bid,
                    duration_ms=existing_audio.duration_ms or 0,
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
        if listen:
            av_contract = build_av_segmentation_contract(raw_text, generated_block_bid)
            speakable_segments = [
                segment.get("text", "")
                for segment in av_contract.get("speakable_segments", [])
            ]
            if not speakable_segments:
                raise_error_with_args(
                    "server.common.paramsError",
                    param_message="No speakable text available for TTS synthesis",
                )

            expected_segment_count = len(speakable_segments)
            existing_by_position: dict[int, LearnGeneratedAudio] = {}
            existing_records = (
                LearnGeneratedAudio.query.filter(
                    LearnGeneratedAudio.generated_block_bid == generated_block_bid,
                    LearnGeneratedAudio.user_bid == user_bid,
                    LearnGeneratedAudio.shifu_bid == shifu_bid,
                    LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
                    LearnGeneratedAudio.deleted == 0,
                )
                .order_by(
                    LearnGeneratedAudio.position.asc(), LearnGeneratedAudio.id.desc()
                )
                .all()
            )
            for record in existing_records:
                pos = int(getattr(record, "position", 0) or 0)
                if pos in existing_by_position:
                    continue
                if not record.oss_url:
                    continue
                existing_by_position[pos] = record

            has_segmented_records = len(existing_by_position) > 1 or any(
                pos > 0 for pos in existing_by_position
            )
            if expected_segment_count > 1 and not has_segmented_records:
                # Existing single-audio records are not compatible with AV mode.
                existing_by_position = {}

            if expected_segment_count and all(
                pos in existing_by_position for pos in range(expected_segment_count)
            ):
                for pos in range(expected_segment_count):
                    record = existing_by_position[pos]
                    yield _build_audio_complete_message(
                        outline_bid=generated_block.outline_item_bid or "",
                        generated_block_bid=generated_block_bid,
                        audio_url=record.oss_url,
                        audio_bid=record.audio_bid,
                        duration_ms=int(record.duration_ms or 0),
                        position=pos,
                        av_contract=av_contract,
                    )
                return

            usage_scene = (
                BILL_USAGE_SCENE_PREVIEW if preview_mode else BILL_USAGE_SCENE_PROD
            )
            usage_metadata = _build_tts_usage_metadata(
                voice_settings=voice_settings,
                audio_settings=audio_settings,
            )

            def _generate_av_audio():
                for position, speakable_text in enumerate(speakable_segments):
                    if position in existing_by_position:
                        record = existing_by_position[position]
                        yield _build_audio_complete_message(
                            outline_bid=generated_block.outline_item_bid or "",
                            generated_block_bid=generated_block_bid,
                            audio_url=record.oss_url,
                            audio_bid=record.audio_bid,
                            duration_ms=int(record.duration_ms or 0),
                            position=position,
                            av_contract=av_contract,
                        )
                        continue

                    cleaned_segment = preprocess_for_tts(speakable_text or "")
                    if not cleaned_segment or len(cleaned_segment.strip()) < 2:
                        continue

                    audio_bid = uuid.uuid4().hex
                    usage_context = _build_tts_usage_context(
                        user_bid=user_bid,
                        shifu_bid=shifu_bid,
                        outline_item_bid=generated_block.outline_item_bid or "",
                        progress_record_bid=generated_block.progress_record_bid or "",
                        generated_block_bid=generated_block_bid,
                        audio_bid=audio_bid,
                        usage_scene=usage_scene,
                    )
                    parent_usage_bid = generate_id(app)
                    stats = {"segment_count": 0, "total_word_count": 0}
                    audio_parts: list[bytes] = []

                    yield from _yield_stream_tts_audio_segments(
                        app=app,
                        text=speakable_text,
                        provider=provider,
                        tts_model=tts_model,
                        voice_settings=voice_settings,
                        audio_settings=audio_settings,
                        usage_context=usage_context,
                        parent_usage_bid=parent_usage_bid,
                        usage_metadata=usage_metadata,
                        outline_bid=generated_block.outline_item_bid or "",
                        generated_block_bid=generated_block_bid,
                        audio_parts=audio_parts,
                        stats=stats,
                        position=position,
                        av_contract=av_contract,
                    )
                    segment_count = int(stats.get("segment_count", 0))
                    total_word_count = int(stats.get("total_word_count", 0))

                    oss_url, duration_ms = _finalize_tts_stream_audio(
                        app,
                        audio_parts=audio_parts,
                        audio_bid=audio_bid,
                        audio_settings=audio_settings,
                        voice_settings=voice_settings,
                        tts_model=tts_model,
                        cleaned_text=cleaned_segment,
                        segment_count=segment_count,
                        persist_audio=True,
                        generated_block_bid=generated_block_bid,
                        progress_record_bid=generated_block.progress_record_bid,
                        user_bid=user_bid,
                        shifu_bid=shifu_bid,
                        position=position,
                    )

                    _record_stream_summary_usage(
                        app,
                        usage_context,
                        usage_bid=parent_usage_bid,
                        provider=provider,
                        tts_model=tts_model,
                        raw_text=speakable_text or "",
                        cleaned_text=cleaned_segment or "",
                        total_word_count=total_word_count,
                        duration_ms=int(duration_ms or 0),
                        segment_count=segment_count,
                        usage_metadata=usage_metadata,
                    )

                    yield _build_audio_complete_message(
                        outline_bid=generated_block.outline_item_bid or "",
                        generated_block_bid=generated_block_bid,
                        audio_url=oss_url,
                        audio_bid=audio_bid,
                        duration_ms=int(duration_ms or 0),
                        position=position,
                        av_contract=av_contract,
                    )

            yield from _yield_with_tts_error_mapping(
                app,
                unknown_error_log="AV TTS synthesis failed",
                body=_generate_av_audio,
            )

            return

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
        usage_context = _build_tts_usage_context(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=generated_block.outline_item_bid or "",
            progress_record_bid=generated_block.progress_record_bid or "",
            generated_block_bid=generated_block_bid,
            audio_bid=audio_bid,
            usage_scene=usage_scene,
        )
        parent_usage_bid = generate_id(app)
        usage_metadata = _build_tts_usage_metadata(
            voice_settings=voice_settings,
            audio_settings=audio_settings,
        )
        stats = {"segment_count": 0, "total_word_count": 0}
        audio_parts: list[bytes] = []

        def _generate_single_audio():
            yield from _yield_stream_tts_audio_segments(
                app=app,
                text=raw_text,
                provider=provider,
                tts_model=tts_model,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                usage_context=usage_context,
                parent_usage_bid=parent_usage_bid,
                usage_metadata=usage_metadata,
                outline_bid=generated_block.outline_item_bid or "",
                generated_block_bid=generated_block_bid,
                audio_parts=audio_parts,
                stats=stats,
            )
            segment_count = int(stats.get("segment_count", 0))
            total_word_count = int(stats.get("total_word_count", 0))

            oss_url, duration_ms = _finalize_tts_stream_audio(
                app,
                audio_parts=audio_parts,
                audio_bid=audio_bid,
                audio_settings=audio_settings,
                voice_settings=voice_settings,
                tts_model=tts_model,
                cleaned_text=cleaned_text,
                segment_count=segment_count,
                persist_audio=True,
                generated_block_bid=generated_block_bid,
                progress_record_bid=generated_block.progress_record_bid,
                user_bid=user_bid,
                shifu_bid=shifu_bid,
            )

            _record_stream_summary_usage(
                app,
                usage_context,
                usage_bid=parent_usage_bid,
                provider=provider,
                tts_model=tts_model,
                raw_text=raw_text,
                cleaned_text=cleaned_text,
                total_word_count=total_word_count,
                duration_ms=int(duration_ms or 0),
                segment_count=segment_count,
                usage_metadata=usage_metadata,
            )

            yield _build_audio_complete_message(
                outline_bid=generated_block.outline_item_bid or "",
                generated_block_bid=generated_block_bid,
                audio_url=oss_url,
                audio_bid=audio_bid,
                duration_ms=int(duration_ms or 0),
            )

        yield from _yield_with_tts_error_mapping(
            app,
            unknown_error_log="TTS streaming synthesis failed",
            body=_generate_single_audio,
        )


def stream_preview_tts_audio(
    app: Flask,
    *,
    shifu_bid: str,
    user_bid: str,
    text: str,
    preview_mode: bool,
):
    with app.app_context():
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
        usage_context = _build_tts_usage_context(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            audio_bid=audio_bid,
            usage_scene=usage_scene,
        )
        parent_usage_bid = generate_id(app)
        usage_metadata = _build_tts_usage_metadata(
            voice_settings=voice_settings,
            audio_settings=audio_settings,
        )
        stats = {"segment_count": 0, "total_word_count": 0}
        audio_parts: list[bytes] = []

        def _generate_preview_audio():
            yield from _yield_stream_tts_audio_segments(
                app=app,
                text=text or "",
                provider=provider,
                tts_model=tts_model,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                usage_context=usage_context,
                parent_usage_bid=parent_usage_bid,
                usage_metadata=usage_metadata,
                outline_bid="",
                generated_block_bid="",
                audio_parts=audio_parts,
                stats=stats,
            )
            segment_count = int(stats.get("segment_count", 0))
            total_word_count = int(stats.get("total_word_count", 0))

            oss_url, duration_ms = _finalize_tts_stream_audio(
                app,
                audio_parts=audio_parts,
                audio_bid=audio_bid,
                audio_settings=audio_settings,
                voice_settings=voice_settings,
                tts_model=tts_model,
                cleaned_text=cleaned_text,
                segment_count=segment_count,
                persist_audio=False,
            )

            _record_stream_summary_usage(
                app,
                usage_context,
                usage_bid=parent_usage_bid,
                provider=provider,
                tts_model=tts_model,
                raw_text=text or "",
                cleaned_text=cleaned_text,
                total_word_count=total_word_count,
                duration_ms=int(duration_ms or 0),
                segment_count=segment_count,
                usage_metadata=usage_metadata,
            )

            yield _build_audio_complete_message(
                outline_bid="",
                generated_block_bid="",
                audio_url=oss_url,
                audio_bid=audio_bid,
                duration_ms=int(duration_ms or 0),
            )

        yield from _yield_with_tts_error_mapping(
            app,
            unknown_error_log="Preview TTS streaming failed",
            body=_generate_preview_audio,
        )
