"""
Shifu draft functions

This module contains functions for managing shifu draft.

Author: yfge
Date: 2025-08-07
"""

from ...dao import db
from datetime import datetime
from .dtos import ShifuDto, ShifuDetailDto
from ...util import generate_id
from ..lesson.const import STATUS_DRAFT
from ..check_risk.funcs import check_text_with_risk_control
from ..common.models import raise_error
from ...common.config import get_config
from .utils import (
    get_shifu_res_url,
    parse_shifu_res_bid,
    get_shifu_res_url_dict,
)
from .models import DraftShifu, AiCourseAuth
from .shifu_history_manager import save_shifu_history
from ..common.dtos import PageNationDTO


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


def return_shifu_draft_dto(shifu_draft: DraftShifu) -> ShifuDetailDto:
    """
    Return shifu draft dto
    Args:
        shifu_draft: Shifu draft
    Returns:
        ShifuDetailDto: Shifu detail dto
    """
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
        shifu_url=get_config("WEB_URL") + "/c/" + shifu_draft.shifu_bid,
        shifu_preview_url=get_config("WEB_URL")
        + "/c/"
        + shifu_draft.shifu_bid
        + "?preview=true",
    )


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
            raise_error("SHIFU.SHIFU_NAME_REQUIRED")
        if len(shifu_name) > 20:
            raise_error("SHIFU.SHIFU_NAME_TOO_LONG")
        if len(shifu_description) > 500:
            raise_error("SHIFU.SHIFU_DESCRIPTION_TOO_LONG")

        # check if the name already exists
        existing_shifu = (
            DraftShifu.query.filter_by(title=shifu_name, deleted=0)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        if existing_shifu:
            raise_error("SHIFU.SHIFU_NAME_ALREADY_EXISTS")
        # create a new DraftShifu object
        shifu_draft: DraftShifu = DraftShifu(
            shifu_bid=shifu_id,
            title=shifu_name,
            description=shifu_description,
            avatar_res_bid=shifu_image,
            keywords=",".join(shifu_keywords) if shifu_keywords else "",
            llm=shifu_model or "",
            llm_temperature=shifu_temperature or 0.3,
            price=shifu_price or 0.0,
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
        db.session.commit()

        return ShifuDto(
            shifu_id=shifu_id,
            shifu_name=shifu_name,
            shifu_description=shifu_description,
            shifu_avatar=shifu_image,
            shifu_state=STATUS_DRAFT,
            is_favorite=False,
        )


def get_shifu_draft_info(app, user_id: str, shifu_id: str) -> ShifuDetailDto:
    """
    Get shifu draft info
    Args:
        app: Flask application instance
        user_id: User ID
        shifu_id: Shifu ID
    Returns:
        ShifuDetailDto: Shifu detail dto
    """
    with app.app_context():
        shifu_draft = get_latest_shifu_draft(shifu_id)
        if not shifu_draft:
            raise_error("SHIFU.SHIFU_NOT_FOUND")
        return return_shifu_draft_dto(shifu_draft)


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
    Returns:
        ShifuDetailDto: Shifu detail dto
    """
    with app.app_context():
        shifu_draft = get_latest_shifu_draft(shifu_id)
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
            new_shifu_draft.updated_user_bid = user_id
            new_shifu_draft.updated_at = datetime.now()
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
        return return_shifu_draft_dto(shifu_draft)


def get_shifu_draft_list(
    app, user_id: str, page_index: int, page_size: int, is_favorite: bool
):
    """
    Get shifu draft list
    Args:
        app: Flask application instance
        user_id: User ID
        page_index: Page index
        page_size: Page size
        is_favorite: Is favorite
    Returns:
        PageNationDTO: Page nation dto
    """
    with app.app_context():
        page_index = max(page_index, 1)
        page_size = max(page_size, 1)
        page_offset = (page_index - 1) * page_size

        created_total = DraftShifu.query.filter(
            DraftShifu.created_user_bid == user_id,
            DraftShifu.deleted == 0,
        ).count()
        shared_total = AiCourseAuth.query.filter(
            AiCourseAuth.user_id == user_id,
        ).count()
        total = created_total + shared_total

        created_subquery = (
            db.session.query(db.func.max(DraftShifu.id))
            .filter(
                DraftShifu.created_user_bid == user_id,
                DraftShifu.deleted == 0,
            )
            .group_by(DraftShifu.shifu_bid)
        )

        shared_course_ids = (
            db.session.query(AiCourseAuth.course_id)
            .filter(AiCourseAuth.user_id == user_id)
            .subquery()
        )

        shared_subquery = (
            db.session.query(db.func.max(DraftShifu.id))
            .filter(
                DraftShifu.shifu_bid.in_(shared_course_ids),
                DraftShifu.deleted == 0,
            )
            .group_by(DraftShifu.shifu_bid)
        )

        union_subquery = created_subquery.union(shared_subquery).subquery()

        shifu_drafts: list[DraftShifu] = (
            db.session.query(DraftShifu)
            .filter(DraftShifu.id.in_(union_subquery))
            .order_by(DraftShifu.id.desc())
            .offset(page_offset)
            .limit(page_size)
            .all()
        )

        infos = [f"{c.shifu_bid} + {c.title} + {c.deleted}\r\n" for c in shifu_drafts]
        app.logger.info(f"{infos}")
        res_bids = [shifu_draft.avatar_res_bid for shifu_draft in shifu_drafts]
        res_url_map = get_shifu_res_url_dict(res_bids)
        shifu_dtos = [
            ShifuDto(
                shifu_draft.shifu_bid,
                shifu_draft.title,
                shifu_draft.description,
                res_url_map.get(shifu_draft.avatar_res_bid, ""),
                STATUS_DRAFT,
                False,
            )
            for shifu_draft in shifu_drafts
        ]
        return PageNationDTO(page_index, page_size, total, shifu_dtos)


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
    Returns:
        ShifuDetailDto: Shifu detail dto
    """
    with app.app_context():
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
            return return_shifu_draft_dto(new_shifu)
