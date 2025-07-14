from ...dao import db
from datetime import datetime
from .dtos import ShifuDto, ShifuDetailDto
from ...util.uuid import generate_id
from ..lesson.const import STATUS_DRAFT
from ..check_risk.funcs import check_text_with_risk_control
from ..common.models import raise_error
from ...common.config import get_config
from .utils import (
    get_shifu_res_url,
    parse_shifu_res_bid,
)
from .models import ShifuDraftShifu

from flaskr.framework.plugin.plugin_manager import extension


@extension("create_shifu")
def create_shifu_draft(
    result,
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
    """ """
    with app.app_context():

        if result and result.shifu_id:
            shifu_id = result.shifu_id
        else:
            shifu_id = generate_id(app)

        if not shifu_name:
            raise_error("SHIFU.SHIFU_NAME_REQUIRED")
        if len(shifu_name) > 20:
            raise_error("SHIFU.SHIFU_NAME_TOO_LONG")
        if len(shifu_description) > 500:
            raise_error("SHIFU.SHIFU_DESCRIPTION_TOO_LONG")

        # check if the name already exists
        existing_shifu = ShifuDraftShifu.query.filter_by(
            title=shifu_name, latest=1, deleted=0
        ).first()
        if existing_shifu:
            raise_error("SHIFU.SHIFU_NAME_ALREADY_EXISTS")
        # create a new ShifuDraftShifu object
        shifu_draft = ShifuDraftShifu(
            shifu_bid=shifu_id,
            title=shifu_name,
            description=shifu_description,
            avatar_res_bid=shifu_image,
            keywords=",".join(shifu_keywords) if shifu_keywords else "",
            llm=shifu_model or "",
            llm_temperature=shifu_temperature or 0.3,
            price=shifu_price or 0.0,
            latest=1,  # mark as the latest version
            version=1,  # the first version
            deleted=0,  # not deleted
            created_user_bid=user_id,
            updated_by_user_bid=user_id,
        )

        # execute risk check
        check_content = f"{shifu_name} {shifu_description}"
        if shifu_keywords:
            check_content += " " + " ".join(shifu_keywords)
        check_text_with_risk_control(app, shifu_id, user_id, check_content)

        # save to database
        db.session.add(shifu_draft)
        db.session.commit()

        return ShifuDto(
            shifu_id=shifu_id,
            shifu_name=shifu_name,
            shifu_description=shifu_description,
            shifu_avatar=shifu_image,
            shifu_state=STATUS_DRAFT,
            is_favorite=False,
        )


@extension("get_shifu_info")
@extension("get_shifu_detail")
def get_shifu_draft_info(result, app, user_id: str, shifu_id: str) -> ShifuDetailDto:
    with app.app_context():
        shifu_draft = ShifuDraftShifu.query.filter_by(
            shifu_bid=shifu_id, latest=1, deleted=0
        ).first()
        if not shifu_draft:
            draft_dto: ShifuDetailDto = result
            shifu_draft = ShifuDraftShifu()
            shifu_draft.bid = draft_dto.bid
            shifu_draft.title = draft_dto.name
            shifu_draft.description = draft_dto.description
            shifu_draft.avatar_res_bid = parse_shifu_res_bid(draft_dto.avatar)
            shifu_draft.keywords = ",".join(draft_dto.keywords)
            shifu_draft.llm = draft_dto.model
            shifu_draft.llm_temperature = draft_dto.temperature
            shifu_draft.price = draft_dto.price
            shifu_draft.latest = 1
            shifu_draft.version = 1
            shifu_draft.deleted = 0
            shifu_draft.created_user_bid = user_id
            shifu_draft.created_at = datetime.now()
            shifu_draft.updated_at = datetime.now()
            shifu_draft.updated_by_user_bid = user_id
            shifu_draft.deleted = 0
            db.session.add(shifu_draft)
            db.session.commit()
        return ShifuDetailDto(
            shifu_id=shifu_draft.bid,
            shifu_name=shifu_draft.title,
            shifu_description=shifu_draft.description,
            shifu_avatar=get_shifu_res_url(app, shifu_draft.avatar_res_bid),
            shifu_keywords=(
                shifu_draft.keywords.split(",") if shifu_draft.keywords else []
            ),
            shifu_model=shifu_draft.llm,
            shifu_temperature=shifu_draft.llm_temperature,
            shifu_price=shifu_draft.price,
            shifu_url=get_config("WEB_URL", "UNCONFIGURED") + "/c/" + shifu_draft.bid,
            shifu_preview_url=get_config("WEB_URL", "UNCONFIGURED")
            + "/c/"
            + shifu_draft.bid
            + "?preview=true",
        )


@extension("save_shifu_info")
@extension("save_shifu_detail")
def save_shifu_draft_info(
    result,
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
    with app.app_context():
        shifu_draft = ShifuDraftShifu.query.filter_by(
            bid=shifu_id, latest=1, deleted=0
        ).first()
        if not shifu_draft:
            shifu_draft = ShifuDraftShifu(
                bid=shifu_id,
                title=shifu_name,
                description=shifu_description,
                avatar_res_bid=shifu_avatar,
                keywords=",".join(shifu_keywords) if shifu_keywords else "",
                llm=shifu_model,
                llm_temperature=shifu_temperature,
                price=shifu_price,
                latest=1,
                version=1,
                deleted=0,
                created_user_bid=user_id,
                updated_by_user_bid=user_id,
            )
            db.session.add(shifu_draft)
            db.session.commit()
        else:
            new_shifu_draft = shifu_draft.clone()
            new_shifu_draft.title = shifu_name
            new_shifu_draft.description = shifu_description
            new_shifu_draft.avatar_res_bid = parse_shifu_res_bid(shifu_avatar)
            new_shifu_draft.keywords = (
                ",".join(shifu_keywords) if shifu_keywords else ""
            )
            new_shifu_draft.llm = shifu_model
            new_shifu_draft.llm_temperature = shifu_temperature
            new_shifu_draft.price = shifu_price
            new_shifu_draft.updated_by_user_bid = user_id
            new_shifu_draft.updated_at = datetime.now()
            app.logger.info(
                f"new_shifu_draft: {new_shifu_draft.id} {new_shifu_draft.version}"
            )
            if not new_shifu_draft.eq(shifu_draft):
                check_text_with_risk_control(
                    app, shifu_id, user_id, new_shifu_draft.get_str_to_check()
                )
                # mark the old version as deleted
                shifu_draft.latest = 0
                db.session.add(new_shifu_draft)
                db.session.commit()
                shifu_draft = new_shifu_draft
        return ShifuDetailDto(
            shifu_id=shifu_draft.bid,
            shifu_name=shifu_draft.title,
            shifu_description=shifu_draft.description,
            shifu_avatar=get_shifu_res_url(app, shifu_draft.avatar_res_bid),
            shifu_keywords=(
                shifu_draft.keywords.split(",") if shifu_draft.keywords else []
            ),
            shifu_model=shifu_draft.llm,
            shifu_temperature=shifu_draft.llm_temperature,
            shifu_price=shifu_draft.price,
            shifu_url=get_config("WEB_URL", "UNCONFIGURED") + "/c/" + shifu_draft.bid,
            shifu_preview_url=get_config("WEB_URL", "UNCONFIGURED")
            + "/c/"
            + shifu_draft.bid
            + "?preview=true",
        )


def get_shifu_draft_list(app, user_id: str, page_index: int, page_size: int):
    with app.app_context():
        shifu_drafts = (
            ShifuDraftShifu.query.filter(
                ShifuDraftShifu.created_user_bid == user_id,
                ShifuDraftShifu.deleted == 0,
            )
            .order_by(ShifuDraftShifu.created_at.desc())
            .paginate(page_index, page_size, False)
        )
        return shifu_drafts


@extension("save_shifu_detail")
def save_shifu_draft_detail(
    result,
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
    with app.app_context():
        shifu_draft = ShifuDraftShifu.query.filter_by(
            bid=shifu_id, latest=1, deleted=0
        ).first()
        if shifu_draft:
            old_check_str = shifu_draft.get_str_to_check()
            new_shifu = shifu_draft.clone()
            new_shifu.course_name = shifu_name
            new_shifu.course_desc = shifu_description
            new_shifu.course_teacher_avatar = shifu_avatar
            new_shifu.course_keywords = ",".join(shifu_keywords)
            new_shifu.course_default_model = shifu_model
            new_shifu.course_price = shifu_price
            new_shifu.course_default_temperature = shifu_temperature
            new_shifu.updated_user_id = user_id
            new_shifu.updated_at = datetime.now()
            new_check_str = new_shifu.get_str_to_check()
            if old_check_str != new_check_str:
                check_text_with_risk_control(app, shifu_id, user_id, new_check_str)
            if not shifu_draft.eq(new_shifu):
                app.logger.info("shifu_draft is not equal to new_shifu,save new_shifu")
                new_shifu.latest = 1
                new_shifu.version = new_shifu.version + 1
                db.session.add(new_shifu)
            db.session.commit()
            return ShifuDetailDto(
                shifu_id=new_shifu.bid,
                shifu_name=new_shifu.title,
                shifu_description=new_shifu.description,
                shifu_avatar=get_shifu_res_url(app, new_shifu.avatar_res_bid),
                shifu_keywords=(
                    new_shifu.keywords.split(",") if new_shifu.keywords else []
                ),
                shifu_model=new_shifu.llm,
                shifu_price=new_shifu.price,
                shifu_temperature=new_shifu.llm_temperature,
                shifu_preview_url=get_config("WEB_URL", "UNCONFIGURED")
                + "/c/"
                + new_shifu.bid
                + "?preview=true&skip=true",
                shifu_url=get_config("WEB_URL", "UNCONFIGURED"),
            )
