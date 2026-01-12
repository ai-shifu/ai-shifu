from markdown_flow import (
    InteractionParser,
)
from flask import Flask, request
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
from flaskr.service.tts.pipeline import synthesize_long_text_to_oss
from flaskr.api.tts import get_default_audio_settings, get_default_voice_settings
from flaskr.service.tts import preprocess_for_tts
from flaskr.service.common import raise_error, raise_error_with_args
from flaskr.service.shifu.utils import get_shifu_res_url
from flaskr.service.shifu.shifu_history_manager import HistoryItem
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
        return LearnShifuInfoDTO(
            bid=shifu.shifu_bid,
            title=shifu.title,
            description=shifu.description,
            avatar=get_shifu_res_url(shifu.avatar_res_bid),
            price=str(shifu.price),
            keywords=shifu.keywords.split(",") if shifu.keywords else [],
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

        # Get audio URLs for generated blocks
        generated_block_bids = [b.generated_block_bid for b in generated_blocks]
        audio_records = LearnGeneratedAudio.query.filter(
            LearnGeneratedAudio.generated_block_bid.in_(generated_block_bids),
            LearnGeneratedAudio.status == AUDIO_STATUS_COMPLETED,
            LearnGeneratedAudio.deleted == 0,
        ).all()
        audio_url_map = {a.generated_block_bid: a.oss_url for a in audio_records}

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

            record = GeneratedBlockDTO(
                generated_block.generated_block_bid,
                content,
                LIKE_STATUS_MAP.get(generated_block.liked, LikeStatus.NONE),
                block_type,
                generated_block.generated_content
                if block_type == BlockType.INTERACTION
                else "",
                audio_url=audio_url_map.get(generated_block.generated_block_bid),
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
        has_next_chapter_button = any(
            record.block_type == BlockType.INTERACTION
            and CONTEXT_INTERACTION_NEXT in record.content
            for record in records
        )
        if (
            progress_record.status == LEARN_STATUS_COMPLETED
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
    if provider == "default":
        provider = ""

    voice_settings = get_default_voice_settings(provider)
    voice_id = (getattr(shifu, "tts_voice_id", "") or "").strip()
    if voice_id:
        voice_settings.voice_id = voice_id

    speed_raw = getattr(shifu, "tts_speed", None)
    if speed_raw is not None:
        voice_settings.speed = float(speed_raw)

    pitch_raw = getattr(shifu, "tts_pitch", None)
    if pitch_raw is not None:
        voice_settings.pitch = int(pitch_raw)

    emotion = (getattr(shifu, "tts_emotion", "") or "").strip()
    if emotion:
        voice_settings.emotion = emotion

    audio_settings = get_default_audio_settings(provider)

    tts_model = (getattr(shifu, "tts_model", "") or "").strip()

    return provider, tts_model, voice_settings, audio_settings


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
            return {
                "audio_url": existing_audio.oss_url,
                "audio_bid": existing_audio.audio_bid,
                "duration_ms": existing_audio.duration_ms,
            }

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
        try:
            result = synthesize_long_text_to_oss(
                app,
                text=raw_text,
                provider_name=provider,
                model=tts_model,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                audio_bid=audio_bid,
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
            oss_object_key="",
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
        try:
            result = synthesize_long_text_to_oss(
                app,
                text=text or "",
                provider_name=provider,
                model=tts_model,
                voice_settings=voice_settings,
                audio_settings=audio_settings,
                audio_bid=audio_bid,
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
