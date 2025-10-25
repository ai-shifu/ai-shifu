from flask import Flask
from ...service.common.dtos import PageNationDTO
from datetime import date as Date
from sqlalchemy import or_

from .models import AuthCredential, UserInfo as UserEntity
from ..profile.models import UserProfile
from .repository import load_user_aggregate


from ...common.swagger import register_schema_to_swagger


@register_schema_to_swagger
class UserItemDTO:
    def __init__(
        self, user_id: str, mobile: str, nickname: str, sex: int, birth: Date
    ) -> None:
        self.user_id = user_id
        self.mobile = mobile
        self.nickname = nickname
        self.sex = sex
        self.birth = birth.strftime("%Y-%m-%d")

    def __json__(self):
        return {
            "user_id": self.user_id,
            "mobile": self.mobile,
            "nickname": self.nickname,
            "sex": self.sex,
            "birth": self.birth,
        }


# get user list
# author: yfge
def get_user_list(app: Flask, page: int = 1, page_size: int = 20, query=None):
    with app.app_context():
        app.logger.info(
            "query:"
            + str(query)
            + " page:"
            + str(page)
            + " page_size:"
            + str(page_size)
        )
        db_query = UserEntity.query.filter(UserEntity.deleted == 0)
        if query:
            if query.get("mobile"):
                mobile = query.get("mobile").strip()
                credential_subquery = (
                    AuthCredential.query.with_entities(AuthCredential.user_bid)
                    .filter(
                        AuthCredential.provider_name == "phone",
                        AuthCredential.identifier.like(f"%{mobile}%"),
                    )
                    .subquery()
                )
                db_query = db_query.filter(
                    or_(
                        UserEntity.user_identify.like(f"%{mobile}%"),
                        UserEntity.user_bid.in_(credential_subquery),
                    )
                )
            if query.get("nickname"):
                nickname = query.get("nickname").strip()
                db_query = db_query.filter(UserEntity.nickname.like(f"%{nickname}%"))
            if query.get("user_id"):
                db_query = db_query.filter(UserEntity.user_bid == query.get("user_id"))
        count = db_query.count()
        if count == 0:
            return {}
        users = (
            db_query.order_by(UserEntity.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = []
        for user in users:
            aggregate = load_user_aggregate(user.user_bid)
            mobile = aggregate.mobile if aggregate else ""
            nickname = aggregate.name if aggregate else user.user_identify
            sex = _resolve_user_sex(user.user_bid)
            birth = _resolve_user_birthday(aggregate)
            items.append(UserItemDTO(user.user_bid, mobile, nickname, sex, birth))
        return PageNationDTO(page, page_size, count, items)


DEFAULT_BIRTHDAY = Date(2003, 1, 1)


def _resolve_user_sex(user_bid: str) -> int:
    profile = (
        UserProfile.query.filter_by(user_id=user_bid, profile_key="sex")
        .order_by(UserProfile.id.desc())
        .first()
    )
    if not profile or profile.profile_value is None:
        return 0
    try:
        return int(profile.profile_value)
    except (TypeError, ValueError):
        return 0


def _resolve_user_birthday(aggregate) -> Date:
    if aggregate and aggregate.birthday:
        return aggregate.birthday
    return DEFAULT_BIRTHDAY
