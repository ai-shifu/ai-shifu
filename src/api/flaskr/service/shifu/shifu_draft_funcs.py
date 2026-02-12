"""
Shifu draft functions

This module contains functions for managing shifu draft.

Author: yfge
Date: 2025-08-07
"""

from typing import Optional
import math

from flask import Flask
from ...dao import db
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from datetime import datetime
from .dtos import ShifuDto, ShifuDetailDto
from ...util import generate_id
from .consts import (
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    SHIFU_NAME_MAX_LENGTH,
    UNIT_TYPE_GUEST,
)
from ..check_risk.funcs import check_text_with_risk_control
from ..common.models import raise_error, raise_error_with_args, AppException
from .utils import (
    get_shifu_res_url,
    parse_shifu_res_bid,
    get_shifu_res_url_dict,
)
from .models import DraftShifu, FavoriteScenario, ShifuUserArchive, PublishedShifu
from .permissions import get_user_shifu_permissions
from .shifu_history_manager import save_shifu_history
from ..common.dtos import PageNationDTO
from ...service.config import get_config
from .funcs import shifu_permission_verification
from .shifu_outline_funcs import create_outline
from flaskr.i18n import _
from ..tts.validation import validate_tts_settings_strict


def get_latest_shifu_draft(shifu_id: str) -> DraftShifu:
    """
    Get the latest shifu draft
    Args:
        shifu_id: Shifu ID
    Returns:
        DraftShifu: Shifu draft
    """
    shifu_draft: DraftShifu = (
        DraftShifu.query.filter(
            DraftShifu.shifu_bid == shifu_id,
            DraftShifu.deleted == 0,
        )
        .order_by(DraftShifu.id.desc())
        .first()
    )
    return shifu_draft


def return_shifu_draft_dto(
    shifu_draft: DraftShifu,
    base_url: str,
    readonly: bool,
    archived_override: Optional[bool] = None,
    can_manage_archive: bool = False,
    can_publish: bool = False,
) -> ShifuDetailDto:
    """
    Return shifu draft dto
    Args:
        shifu_draft: Shifu draft
        base_url: Base URL to build shifu links
        readonly: Whether the current user has read-only permission
        archived_override: Optional override for archived state (per-user)
    Returns:
        ShifuDetailDto: Shifu detail dto
    """
    normalized_base = base_url.rstrip("/") if base_url else ""
    shifu_path = f"/c/{shifu_draft.shifu_bid}"
    shifu_url = f"{normalized_base}{shifu_path}" if normalized_base else shifu_path
    shifu_preview_url = (
        f"{shifu_url}?preview=true" if normalized_base else f"{shifu_path}?preview=true"
    )

    stored_provider = getattr(shifu_draft, "tts_provider", "") or ""

    return ShifuDetailDto(
        shifu_id=shifu_draft.shifu_bid,
        shifu_name=shifu_draft.title,
        shifu_description=shifu_draft.description,
        shifu_avatar=get_shifu_res_url(shifu_draft.avatar_res_bid),
        shifu_keywords=(
            shifu_draft.keywords.split(",") if shifu_draft.keywords else []
        ),
        shifu_model=shifu_draft.llm,
        shifu_temperature=shifu_draft.llm_temperature,
        shifu_price=shifu_draft.price,
        shifu_url=shifu_url,
        shifu_preview_url=shifu_preview_url,
        shifu_system_prompt=shifu_draft.llm_system_prompt,
        readonly=readonly,
        archived=bool(archived_override) if archived_override is not None else False,
        can_manage_archive=can_manage_archive,
        can_publish=can_publish,
        created_user_bid=shifu_draft.created_user_bid or "",
        tts_enabled=bool(shifu_draft.tts_enabled),
        tts_provider=stored_provider,
        tts_model=getattr(shifu_draft, "tts_model", "") or "",
        tts_voice_id=shifu_draft.tts_voice_id or "",
        tts_speed=float(shifu_draft.tts_speed)
        if shifu_draft.tts_speed is not None
        else 1.0,
        tts_pitch=int(shifu_draft.tts_pitch) if shifu_draft.tts_pitch else 0,
        tts_emotion=shifu_draft.tts_emotion or "",
        use_learner_language=bool(getattr(shifu_draft, "use_learner_language", 0)),
    )


def _get_user_archive_map(app, user_id: str, shifu_ids: list[str]) -> dict[str, bool]:
    """
    Load per-user archive states for the given shifu ids.
    """
    if not shifu_ids:
        return {}
    with app.app_context():
        records = ShifuUserArchive.query.filter(
            ShifuUserArchive.user_bid == user_id,
            ShifuUserArchive.shifu_bid.in_(shifu_ids),
        ).all()
        return {record.shifu_bid: bool(record.archived) for record in records}


def create_shifu_draft(
    app,
    user_id: str,
    shifu_name: str,
    shifu_description: str,
    shifu_image: str,
    shifu_keywords: list[str] = None,
    shifu_model: str = None,
    shifu_temperature: float = None,
    shifu_price: float = None,
):
    """
    Create a shifu draft
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_name: Shifu name
        shifu_description: Shifu description
        shifu_image: Shifu image
        shifu_keywords: Shifu keywords
        shifu_model: Shifu model
        shifu_temperature: Shifu temperature
        shifu_price: Shifu price
    Returns:
        ShifuDto: Shifu dto
    """
    with app.app_context():
        now_time = datetime.now()

        shifu_id = generate_id(app)

        if not shifu_name:
            raise_error("server.shifu.shifuNameRequired")
        if len(shifu_name) > SHIFU_NAME_MAX_LENGTH:
            raise_error_with_args(
                "server.shifu.shifuNameTooLong", max_length=SHIFU_NAME_MAX_LENGTH
            )
        if len(shifu_description) > 500:
            raise_error("server.shifu.shifuDescriptionTooLong")

        # check if the name already exists
        existing_shifu = (
            DraftShifu.query.filter_by(title=shifu_name, deleted=0)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        if existing_shifu:
            raise_error("server.shifu.shifuNameAlreadyExists")
        # create a new DraftShifu object
        shifu_draft: DraftShifu = DraftShifu(
            shifu_bid=shifu_id,
            title=shifu_name,
            description=shifu_description,
            avatar_res_bid=shifu_image,
            keywords=",".join(shifu_keywords) if shifu_keywords else "",
            llm=shifu_model or "",
            llm_temperature=shifu_temperature or 0.3,
            price=shifu_price or get_config("MIN_SHIFU_PRICE"),
            deleted=0,  # not deleted
            created_user_bid=user_id,
            created_at=now_time,
            updated_user_bid=user_id,
            updated_at=now_time,
        )

        # execute risk check
        check_content = f"{shifu_name} {shifu_description}"
        if shifu_keywords:
            check_content += " " + " ".join(shifu_keywords)
        check_text_with_risk_control(app, shifu_id, user_id, check_content)

        # save to database
        db.session.add(shifu_draft)
        db.session.flush()

        save_shifu_history(app, user_id, shifu_id, shifu_draft.id)

        # Initialize default chapter and lesson
        try:
            # Get default names using i18n system
            chapter_name = _("server.shifu.defaultChapterName")
            lesson_name = _("server.shifu.defaultLessonName")

            # Create default chapter
            chapter = create_outline(
                app=app,
                user_id=user_id,
                shifu_id=shifu_id,
                parent_id="",  # Root level
                outline_name=chapter_name,
                outline_description="",
                outline_index=0,
                outline_type=UNIT_TYPE_GUEST,
                system_prompt=None,
                is_hidden=False,
            )

            # Create default lesson under the chapter
            create_outline(
                app=app,
                user_id=user_id,
                shifu_id=shifu_id,
                parent_id=chapter.bid,  # Under the chapter
                outline_name=lesson_name,
                outline_description="",
                outline_index=0,
                outline_type=UNIT_TYPE_GUEST,
                system_prompt=None,
                is_hidden=False,
            )

        except (AppException, SQLAlchemyError, IntegrityError) as e:
            app.logger.warning(
                f"Failed to initialize default chapter and lesson: "
                f"{type(e).__name__}: {e}"
            )
            # Don't fail the entire creation process if chapter initialization fails

        db.session.commit()

        return ShifuDto(
            shifu_id=shifu_id,
            shifu_name=shifu_name,
            shifu_description=shifu_description,
            shifu_avatar=shifu_image,
            shifu_state=STATUS_DRAFT,
            is_favorite=False,
            archived=False,
        )


def get_shifu_draft_info(
    app, user_id: str, shifu_id: str, base_url: str
) -> ShifuDetailDto:
    """
    Get shifu draft info
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        base_url: Base URL to build shifu links
    Returns:
        ShifuDetailDto: Shifu detail dto
    """
    with app.app_context():
        shifu_draft = get_latest_shifu_draft(shifu_id)
        if not shifu_draft:
            raise_error("server.shifu.shifuNotFound")
        permission_map = get_user_shifu_permissions(app, user_id)
        has_view_permission = (
            shifu_id in permission_map
            or shifu_permission_verification(app, user_id, shifu_id, "view")
        )
        has_edit_permission = shifu_permission_verification(
            app, user_id, shifu_id, "edit"
        )
        has_publish_permission = shifu_permission_verification(
            app, user_id, shifu_id, "publish"
        )
        readonly = not has_edit_permission
        archive_map = _get_user_archive_map(app, user_id, [shifu_id])
        archived_override = archive_map.get(shifu_id)
        return return_shifu_draft_dto(
            shifu_draft,
            base_url,
            readonly,
            archived_override,
            can_manage_archive=has_view_permission,
            can_publish=has_publish_permission,
        )


def save_shifu_draft_info(
    app,
    user_id: str,
    shifu_id: str,
    shifu_name: str,
    shifu_description: str,
    shifu_avatar: str,
    shifu_keywords: list[str],
    shifu_model: str,
    shifu_temperature: float,
    shifu_price: float,
    shifu_system_prompt: str,
    base_url: str,
    tts_enabled: bool = False,
    tts_provider: str = "",
    tts_model: str = "",
    tts_voice_id: str = "",
    tts_speed: float = 1.0,
    tts_pitch: int = 0,
    tts_emotion: str = "",
    use_learner_language: bool = False,
):
    """
    Save shifu draft info
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        shifu_name: Shifu name
        shifu_description: Shifu description
        shifu_avatar: Shifu avatar
        shifu_keywords: Shifu keywords
        shifu_model: Shifu model
        shifu_temperature: Shifu temperature
        shifu_price: Shifu price
        shifu_system_prompt: Shifu system prompt
        base_url: Base URL to build shifu links
        tts_enabled: Whether TTS is enabled
        tts_provider: TTS provider (minimax, volcengine, volcengine_http, baidu, aliyun)
        tts_model: TTS model/resource ID
        tts_voice_id: TTS voice ID
        tts_speed: TTS speech speed
        tts_pitch: TTS pitch adjustment
        tts_emotion: TTS emotion setting
        use_learner_language: Whether to use learner's language for AI output
    Returns:
        ShifuDetailDto: Shifu detail dto
    """
    with app.app_context():
        if tts_enabled:
            validated = validate_tts_settings_strict(
                provider=tts_provider,
                model=tts_model,
                voice_id=tts_voice_id,
                speed=tts_speed,
                pitch=tts_pitch,
                emotion=tts_emotion,
            )
            tts_provider = validated.provider
            tts_model = validated.model
            tts_voice_id = validated.voice_id
            tts_speed = validated.speed
            tts_pitch = validated.pitch
            tts_emotion = validated.emotion

        # Validate input lengths
        if len(shifu_name) > SHIFU_NAME_MAX_LENGTH:
            raise_error_with_args(
                "server.shifu.shifuNameTooLong", max_length=SHIFU_NAME_MAX_LENGTH
            )
        if len(shifu_description) > 500:
            raise_error("server.shifu.shifuDescriptionTooLong")

        shifu_draft = get_latest_shifu_draft(shifu_id)
        min_shifu_price = get_config("MIN_SHIFU_PRICE")
        if shifu_price < min_shifu_price:
            raise_error_with_args(
                "server.shifu.shifuPriceTooLow", min_shifu_price=min_shifu_price
            )
        if not shifu_draft:
            shifu_draft: DraftShifu = DraftShifu(
                shifu_bid=shifu_id,
                title=shifu_name,
                description=shifu_description,
                avatar_res_bid=shifu_avatar,
                keywords=",".join(shifu_keywords) if shifu_keywords else "",
                llm=shifu_model,
                llm_temperature=shifu_temperature,
                price=shifu_price,
                llm_system_prompt=shifu_system_prompt if shifu_system_prompt else "",
                tts_enabled=1 if tts_enabled else 0,
                tts_provider=tts_provider or "",
                tts_model=tts_model or "",
                tts_voice_id=tts_voice_id or "",
                tts_speed=tts_speed,
                tts_pitch=tts_pitch,
                tts_emotion=tts_emotion or "",
                use_learner_language=1 if use_learner_language else 0,
                deleted=0,
                created_user_bid=user_id,
                updated_user_bid=user_id,
            )
            db.session.add(shifu_draft)
            db.session.flush()
            save_shifu_history(app, user_id, shifu_id, shifu_draft.id)
            db.session.commit()
        else:
            new_shifu_draft: DraftShifu = shifu_draft.clone()
            new_shifu_draft.title = shifu_name
            new_shifu_draft.description = shifu_description
            new_shifu_draft.avatar_res_bid = parse_shifu_res_bid(shifu_avatar)
            new_shifu_draft.keywords = (
                ",".join(shifu_keywords) if shifu_keywords else ""
            )
            new_shifu_draft.llm = shifu_model
            new_shifu_draft.llm_temperature = shifu_temperature
            new_shifu_draft.price = shifu_price
            new_shifu_draft.tts_enabled = 1 if tts_enabled else 0
            new_shifu_draft.tts_provider = tts_provider or ""
            new_shifu_draft.tts_model = tts_model or ""
            new_shifu_draft.tts_voice_id = tts_voice_id or ""
            new_shifu_draft.tts_speed = tts_speed
            new_shifu_draft.tts_pitch = tts_pitch
            new_shifu_draft.tts_emotion = tts_emotion or ""
            new_shifu_draft.use_learner_language = 1 if use_learner_language else 0
            new_shifu_draft.updated_user_bid = user_id
            new_shifu_draft.updated_at = datetime.now()
            if shifu_system_prompt is not None:
                new_shifu_draft.llm_system_prompt = shifu_system_prompt
            if not new_shifu_draft.eq(shifu_draft):
                check_text_with_risk_control(
                    app, shifu_id, user_id, new_shifu_draft.get_str_to_check()
                )
                # mark the old version as deleted
                db.session.add(new_shifu_draft)
                db.session.flush()
                save_shifu_history(app, user_id, shifu_id, new_shifu_draft.id)
                db.session.commit()
                shifu_draft = new_shifu_draft
        has_edit_permission = shifu_permission_verification(
            app, user_id, shifu_id, "edit"
        )
        has_view_permission = shifu_permission_verification(
            app, user_id, shifu_id, "view"
        )
        has_publish_permission = shifu_permission_verification(
            app, user_id, shifu_id, "publish"
        )
        readonly = not has_edit_permission
        archive_map = _get_user_archive_map(app, user_id, [shifu_id])
        archived_override = archive_map.get(shifu_id)
        return return_shifu_draft_dto(
            shifu_draft,
            base_url,
            readonly,
            archived_override,
            can_manage_archive=has_view_permission,
            can_publish=has_publish_permission,
        )


def get_shifu_draft_list(
    app,
    user_id: str,
    page_index: int,
    page_size: int,
    is_favorite: bool,
    archived: bool = False,
    creator_only: bool = False,
):
    """
    Get shifu draft list
    Args:
        app: Flask application instance
        user_id: User ID
        page_index: Page index
        page_size: Page size
        is_favorite: Is favorite
        archived: Filter archived (True) or active (False) shifus
        creator_only: Only include shifus created by the user
    Returns:
        PageNationDTO: Page nation dto
    """
    with app.app_context():
        page_index = max(page_index, 1)
        page_size = max(page_size, 1)

        if creator_only:
            shifu_bids = get_user_created_shifu_bids(app, user_id)
        else:
            permission_map = get_user_shifu_permissions(app, user_id)
            shifu_bids = list(permission_map.keys())
        if not shifu_bids:
            return PageNationDTO(page_index, page_size, 0, [])

        latest_subquery = (
            db.session.query(db.func.max(DraftShifu.id))
            .filter(
                DraftShifu.shifu_bid.in_(shifu_bids),
                DraftShifu.deleted == 0,
            )
            .group_by(DraftShifu.shifu_bid)
        ).subquery()

        shifu_drafts: list[DraftShifu] = (
            db.session.query(DraftShifu)
            .filter(DraftShifu.id.in_(latest_subquery))
            .order_by(DraftShifu.title.asc(), DraftShifu.shifu_bid.asc())
            .all()
        )

        if is_favorite:
            favorite_ids = {
                fav.scenario_id
                for fav in FavoriteScenario.query.filter(
                    FavoriteScenario.user_id == user_id,
                    FavoriteScenario.status == 1,
                ).all()
            }
            shifu_drafts = [
                draft for draft in shifu_drafts if draft.shifu_bid in favorite_ids
            ]

        archive_map = _get_user_archive_map(
            app, user_id, [draft.shifu_bid for draft in shifu_drafts]
        )

        def is_archived(draft: DraftShifu) -> bool:
            return bool(archive_map.get(draft.shifu_bid))

        filtered_shifus = [
            draft for draft in shifu_drafts if is_archived(draft) == archived
        ]

        total = len(filtered_shifus)
        page_count = math.ceil(total / page_size) if page_size > 0 else 0
        safe_page_index = min(page_index, max(page_count, 1))
        page_offset = (safe_page_index - 1) * page_size
        shifu_drafts = filtered_shifus[page_offset : page_offset + page_size]

        app.logger.debug(
            "Fetched %d shifus for user %s (archived=%s, favorite=%s)",
            len(shifu_drafts),
            user_id,
            archived,
            is_favorite,
        )
        res_bids = [shifu_draft.avatar_res_bid for shifu_draft in shifu_drafts]
        res_url_map = get_shifu_res_url_dict(res_bids)
        shifu_dtos = [
            ShifuDto(
                shifu_draft.shifu_bid,
                shifu_draft.title,
                shifu_draft.description,
                res_url_map.get(shifu_draft.avatar_res_bid, ""),
                STATUS_DRAFT,
                bool(is_favorite),
                is_archived(shifu_draft),
            )
            for shifu_draft in shifu_drafts
        ]
        return PageNationDTO(safe_page_index, page_size, total, shifu_dtos)


def get_user_created_shifu_bids(app: Flask, user_id: str) -> list[str]:
    """Return shifu bids created by the specified user."""
    with app.app_context():
        rows = (
            db.session.query(DraftShifu.shifu_bid)
            .filter(
                DraftShifu.created_user_bid == user_id,
                DraftShifu.deleted == 0,
            )
            .distinct()
            .all()
        )
        return [row[0] for row in rows if row and row[0]]


def get_user_created_published_shifu_bids(app: Flask, user_id: str) -> list[str]:
    """Return published shifu bids created by the specified user."""
    with app.app_context():
        rows = (
            db.session.query(PublishedShifu.shifu_bid)
            .filter(
                PublishedShifu.created_user_bid == user_id,
                PublishedShifu.deleted == 0,
            )
            .distinct()
            .all()
        )
        return [row[0] for row in rows if row and row[0]]


def get_shifu_published_list(
    app,
    user_id: str,
    page_index: int,
    page_size: int,
    creator_only: bool = True,
):
    """Get published shifu list."""
    with app.app_context():
        page_index = max(page_index, 1)
        page_size = max(page_size, 1)

        if creator_only:
            shifu_bids = get_user_created_published_shifu_bids(app, user_id)
        else:
            permission_map = get_user_shifu_permissions(app, user_id)
            shifu_bids = list(permission_map.keys())
        if not shifu_bids:
            return PageNationDTO(page_index, page_size, 0, [])

        latest_subquery = (
            db.session.query(db.func.max(PublishedShifu.id))
            .filter(
                PublishedShifu.shifu_bid.in_(shifu_bids),
                PublishedShifu.deleted == 0,
            )
            .group_by(PublishedShifu.shifu_bid)
        ).subquery()

        base_query = (
            db.session.query(PublishedShifu)
            .filter(PublishedShifu.id.in_(latest_subquery))
            .order_by(PublishedShifu.title.asc(), PublishedShifu.shifu_bid.asc())
        )

        total = base_query.order_by(None).count()
        page_count = math.ceil(total / page_size) if page_size > 0 else 0
        safe_page_index = min(page_index, max(page_count, 1))
        page_offset = (safe_page_index - 1) * page_size
        shifus: list[PublishedShifu] = (
            base_query.limit(page_size).offset(page_offset).all()
        )

        res_bids = [shifu.avatar_res_bid for shifu in shifus]
        res_url_map = get_shifu_res_url_dict(res_bids)
        shifu_dtos = [
            ShifuDto(
                shifu.shifu_bid,
                shifu.title,
                shifu.description,
                res_url_map.get(shifu.avatar_res_bid, ""),
                STATUS_PUBLISHED,
                False,
                False,
            )
            for shifu in shifus
        ]
        return PageNationDTO(safe_page_index, page_size, total, shifu_dtos)


def _set_shifu_archive_state(app, user_id: str, shifu_id: str, archived: bool):
    with app.app_context():
        shifu_draft = get_latest_shifu_draft(shifu_id)
        if not shifu_draft:
            raise_error("server.shifu.shifuNotFound")
        permission_map = get_user_shifu_permissions(app, user_id)
        if shifu_id not in permission_map:
            raise_error("server.shifu.noPermission")

        new_flag = 1 if archived else 0
        now = datetime.now()
        existing = ShifuUserArchive.query.filter(
            ShifuUserArchive.shifu_bid == shifu_id,
            ShifuUserArchive.user_bid == user_id,
        ).first()

        if existing:
            existing.archived = new_flag
            existing.archived_at = now if archived else None
            existing.updated_at = now
        else:
            db.session.add(
                ShifuUserArchive(
                    shifu_bid=shifu_id,
                    user_bid=user_id,
                    archived=new_flag,
                    archived_at=now if archived else None,
                    created_at=now,
                    updated_at=now,
                )
            )

        db.session.commit()


def archive_shifu(app, user_id: str, shifu_id: str):
    _set_shifu_archive_state(app, user_id, shifu_id, True)


def unarchive_shifu(app, user_id: str, shifu_id: str):
    _set_shifu_archive_state(app, user_id, shifu_id, False)


def save_shifu_draft_detail(
    app,
    user_id: str,
    shifu_id: str,
    shifu_name: str,
    shifu_description: str,
    shifu_avatar: str,
    shifu_keywords: list[str],
    shifu_model: str,
    shifu_price: float,
    shifu_temperature: float,
    base_url: str,
):
    """
    Save shifu draft detail
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
        shifu_name: Shifu name
        shifu_description: Shifu description
        shifu_avatar: Shifu avatar
        shifu_keywords: Shifu keywords
        shifu_model: Shifu model
        shifu_price: Shifu price
        shifu_temperature: Shifu temperature
        base_url: Base URL to build shifu links
    Returns:
        ShifuDetailDto: Shifu detail dto
    """
    with app.app_context():
        # Validate input lengths
        if len(shifu_name) > SHIFU_NAME_MAX_LENGTH:
            raise_error_with_args(
                "server.shifu.shifuNameTooLong", max_length=SHIFU_NAME_MAX_LENGTH
            )
        if len(shifu_description) > 500:
            raise_error("server.shifu.shifuDescriptionTooLong")

        shifu_draft = get_latest_shifu_draft(shifu_id)
        if shifu_draft:
            old_check_str = shifu_draft.get_str_to_check()
            new_shifu = shifu_draft.clone()
            new_shifu.title = shifu_name
            new_shifu.description = shifu_description
            new_shifu.avatar_res_bid = parse_shifu_res_bid(shifu_avatar)
            new_shifu.keywords = ",".join(shifu_keywords)
            new_shifu.llm = shifu_model
            new_shifu.price = shifu_price
            new_shifu.llm_temperature = shifu_temperature
            new_shifu.updated_user_bid = user_id
            new_shifu.updated_at = datetime.now()
            new_check_str = new_shifu.get_str_to_check()
            if old_check_str != new_check_str:
                check_text_with_risk_control(app, shifu_id, user_id, new_check_str)
            if not shifu_draft.eq(new_shifu):
                app.logger.info("shifu_draft is not equal to new_shifu,save new_shifu")
                db.session.add(new_shifu)
                db.session.flush()
                save_shifu_history(app, user_id, shifu_id, new_shifu.id)
            db.session.commit()
            has_edit_permission = shifu_permission_verification(
                app, user_id, shifu_id, "edit"
            )
            has_view_permission = shifu_permission_verification(
                app, user_id, shifu_id, "view"
            )
            has_publish_permission = shifu_permission_verification(
                app, user_id, shifu_id, "publish"
            )
            readonly = not has_edit_permission
            archive_map = _get_user_archive_map(app, user_id, [shifu_id])
            archived_override = archive_map.get(shifu_id)
            return return_shifu_draft_dto(
                new_shifu,
                base_url,
                readonly,
                archived_override,
                can_manage_archive=has_view_permission,
                can_publish=has_publish_permission,
            )
