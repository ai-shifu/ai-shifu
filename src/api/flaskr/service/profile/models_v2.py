from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    SmallInteger,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func

from ...dao import db


class UserProfile(db.Model):
    """
    User profile values (append-only history).
    """

    __tablename__ = "profile_user_profiles"
    __table_args__ = {"comment": "Profile user profiles"}

    id = Column(BIGINT, primary_key=True, autoincrement=True)

    user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="User business identifier",
    )

    profile_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Profile item business identifier",
    )

    profile_key = Column(
        String(255),
        nullable=False,
        default="",
        index=True,
        comment="Profile key",
    )

    profile_value = Column(
        Text,
        nullable=False,
        default="",
        comment="Profile value",
    )

    profile_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment=(
            "Profile type: 2900=input_unconf, 2901=input_text, 2902=input_number, "
            "2903=input_select, 2904=input_sex, 2905=input_date"
        ),
    )

    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag: 0=active, 1=deleted",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Creation timestamp",
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp",
    )


class ProfileItem(db.Model):
    """
    Profile item definitions.
    """

    __tablename__ = "profile_items"
    __table_args__ = (
        UniqueConstraint("profile_item_bid", name="uk_profile_items_bid"),
        {"comment": "Profile items"},
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True)

    profile_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Profile item business identifier",
    )

    shifu_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Shifu business identifier (empty for system)",
    )

    profile_index = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Profile index",
    )

    profile_key = Column(
        String(255),
        nullable=False,
        default="",
        index=True,
        comment="Profile key",
    )

    profile_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment=(
            "Profile type: 2900=input_unconf, 2901=input_text, 2902=input_number, "
            "2903=input_select, 2904=input_sex, 2905=input_date"
        ),
    )

    profile_value_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Profile value type: 3001=all, 3002=specific",
    )

    profile_show_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Profile show type: 3001=all, 3002=user, 3003=course, 3004=hidden",
    )

    profile_remark = Column(
        Text,
        nullable=False,
        default="",
        comment="Profile remark",
    )

    profile_prompt_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Profile prompt type: 3101=profile, 3102=item",
    )

    profile_raw_prompt = Column(
        Text,
        nullable=False,
        default="",
        comment="Profile raw prompt",
    )

    profile_prompt = Column(
        Text,
        nullable=False,
        default="",
        comment="Profile prompt",
    )

    profile_prompt_model = Column(
        Text,
        nullable=False,
        default="",
        comment="Profile prompt model",
    )

    profile_prompt_model_args = Column(
        Text,
        nullable=False,
        default="",
        comment="Profile prompt model args",
    )

    profile_color_setting = Column(
        String(255),
        nullable=False,
        default="",
        comment="Profile color",
    )

    profile_script_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Profile script business identifier",
    )

    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag: 0=active, 1=deleted",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Creation timestamp",
    )

    created_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator user business identifier",
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp",
    )

    updated_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Last updater user business identifier",
    )


class ProfileItemValue(db.Model):
    """
    Profile item values (only for option type).
    """

    __tablename__ = "profile_item_values"
    __table_args__ = (
        UniqueConstraint("profile_item_value_bid", name="uk_profile_item_values_bid"),
        {"comment": "Profile item values"},
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True)

    profile_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Profile item business identifier",
    )

    profile_item_value_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Profile item value business identifier",
    )

    profile_value = Column(
        Text,
        nullable=False,
        default="",
        comment="Profile value",
    )

    profile_value_index = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Profile value index",
    )

    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag: 0=active, 1=deleted",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Creation timestamp",
    )

    created_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator user business identifier",
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp",
    )

    updated_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Last updater user business identifier",
    )


class ProfileItemI18n(db.Model):
    """
    Profile i18n entries (remark/label per language).
    """

    __tablename__ = "profile_item_i18ns"
    __table_args__ = {"comment": "Profile item i18n"}

    id = Column(BIGINT, primary_key=True, autoincrement=True)

    parent_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Parent business identifier",
    )

    conf_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Profile conf type: 3101=profile, 3102=item",
    )

    language = Column(
        String(255),
        nullable=False,
        default="",
        index=True,
        comment="Language",
    )

    profile_item_remark = Column(
        Text,
        nullable=False,
        default="",
        comment="Profile item remark",
    )

    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        index=True,
        comment="Deletion flag: 0=active, 1=deleted",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        comment="Creation timestamp",
    )

    created_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Creator user business identifier",
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update timestamp",
    )

    updated_user_bid = Column(
        String(36),
        nullable=False,
        default="",
        index=True,
        comment="Last updater user business identifier",
    )
