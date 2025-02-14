from sqlalchemy import (
    Column,
    String,
    Integer,
    TIMESTAMP,
    Text,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db


PROFILE_TYPE_SYSTEM = 2801
PROFILE_TYPE_USER = 2802
PROFILE_TYPE_PLATFORM = 2803
PROFILE_TYPE_COURSE = 2804
PROFILE_TYPE_COURSE_SECTION = 2805
PROFILE_TYPE_TEMP = 2806


PROFILE_TYPE_INPUT_TEXT = 2901
PROFILE_TYPE_INPUT_NUMBER = 2902
PROFILE_TYPE_INPUT_SELECT = 2903
PROFILE_TYPE_INPUT_SEX = 2904
PROFILE_TYPE_INPUT_DATE = 2905


PROFILE_SHOW_TYPE_ALL = 3001
PROFILE_SHOW_TYPE_USER = 3002
PROFILE_SHOW_TYPE_PLATFORM = 3003
PROFILE_SHOW_TYPE_COURSE = 3004

PROFILE_CONF_TYPE_PROFILE = 3101
PROFILE_CONF_TYPE_ITEM = 3102


class UserProfile(db.Model):
    __tablename__ = "user_profile"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    user_id = Column(
        String(36), nullable=False, default="", comment="User UUID", index=True
    )
    profile_id = Column(
        String(36), nullable=False, comment="Profile ID", index=True, default=""
    )
    profile_key = Column(
        String(255), nullable=False, default="", comment="Profile key", index=True
    )
    profile_value = Column(Text, nullable=False, comment="Profile value")
    profile_type = Column(
        Integer,
        nullable=False,
        default=0,
        comment="",
    )
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )
    status = Column(
        Integer, nullable=False, default=1, comment="0 for deleted, 1 for active"
    )


class ProfileItem(db.Model):
    __tablename__ = "profile_item"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    profile_id = Column(BIGINT, nullable=False, comment="Profile ID", unique=True)
    parent_id = Column(
        String(36), nullable=False, default="", comment="parent_id", index=True
    )
    profile_index = Column(Integer, nullable=False, default=0, comment="Profile index")
    profile_key = Column(
        String(255), nullable=False, default="", comment="Profile key", index=True
    )
    profile_type = Column(Integer, nullable=False, default=0, comment="")
    profile_value_type = Column(Integer, nullable=False, default=0, comment="")
    profile_show_type = Column(Integer, nullable=False, default=0, comment="")
    profile_remark = Column(Text, nullable=False, comment="Profile remark")
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )
    status = Column(
        Integer, nullable=False, default=0, comment="0 for deleted, 1 for active"
    )
    created_by = Column(String(36), nullable=False, default="", comment="Created by")
    updated_by = Column(String(36), nullable=False, default="", comment="Updated by")


class ProfileItemValue(db.Model):
    __tablename__ = "profile_item_value"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    profile_id = Column(BIGINT, nullable=False, comment="Profile ID", index=True)
    profile_item_id = Column(
        BIGINT, nullable=False, comment="Profile item ID", index=True
    )
    profile_value = Column(Text, nullable=False, comment="Profile value")
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )
    status = Column(
        Integer, nullable=False, default=0, comment="0 for deleted, 1 for active"
    )
    created_by = Column(String(36), nullable=False, default="", comment="Created by")
    updated_by = Column(String(36), nullable=False, default="", comment="Updated by")


class ProfileItemI18n(db.Model):
    __tablename__ = "profile_item_i18n"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    parent_id = Column(
        String(36), nullable=False, default="", comment="parent_id", index=True
    )
    conf_type = Column(Integer, nullable=False, default=0, comment="")
    language = Column(String(255), nullable=False, comment="Language", index=True)
    profile_item_remark = Column(Text, nullable=False, comment="Profile item remark")
    created = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )
    status = Column(
        Integer, nullable=False, default=0, comment="0 for deleted, 1 for active"
    )
    created_by = Column(String(36), nullable=False, default="", comment="Created by")
    updated_by = Column(String(36), nullable=False, default="", comment="Updated by")
