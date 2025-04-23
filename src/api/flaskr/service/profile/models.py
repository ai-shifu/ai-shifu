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
PROFILE_TYPE_COURSE = 2803
PROFILE_TYPE_COURSE_SECTION = 2804
PROFILE_TYPE_TEMP = 2805


PROFILE_TYPE_INPUT_UNCONF = 2900
PROFILE_TYPE_INPUT_TEXT = 2901
PROFILE_TYPE_INPUT_NUMBER = 2902
PROFILE_TYPE_INPUT_SELECT = 2903
PROFILE_TYPE_INPUT_SEX = 2904
PROFILE_TYPE_INPUT_DATE = 2905


PROFILE_SHOW_TYPE_ALL = 3001
PROFILE_SHOW_TYPE_USER = 3002
PROFILE_SHOW_TYPE_COURSE = 3003
PROFILE_SHOW_TYPE_HIDDEN = 3004

PROFILE_CONF_TYPE_PROFILE = 3101
PROFILE_CONF_TYPE_ITEM = 3102


CONST_PROFILE_TYPE_TEXT = "text"
CONST_PROFILE_TYPE_OPTION = "option"

PROFILE_TYPE_VLUES = {
    CONST_PROFILE_TYPE_TEXT: PROFILE_TYPE_INPUT_TEXT,
    CONST_PROFILE_TYPE_OPTION: PROFILE_TYPE_INPUT_SELECT,
}


CONST_PROFILE_SCOPE_USER = "user"
CONST_PROFILE_SCOPE_SYSTEM = "system"


# table to save user profile
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


# table to save profile item / definations
class ProfileItem(db.Model):
    __tablename__ = "profile_item"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    profile_id = Column(String(36), nullable=False, comment="Profile ID", unique=True)
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
    profile_prompt_type = Column(Integer, nullable=False, default=0, comment="")
    profile_raw_prompt = Column(
        Text, nullable=False, default="", comment="Profile raw prompt"
    )
    profile_prompt = Column(Text, nullable=False, default="", comment="Profile prompt")
    profile_prompt_model = Column(
        Text, nullable=False, default="", comment="Profile prompt model"
    )
    profile_prompt_model_args = Column(
        Text, nullable=False, default="", comment="Profile prompt model args"
    )
    profile_color_setting = Column(
        String(255), nullable=False, default="", comment="Profile color"
    )
    profile_script_id = Column(
        String(36), nullable=False, default="", comment="Profile script id", index=True
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
        Integer, nullable=False, default=0, comment="0 for deleted, 1 for active"
    )
    created_by = Column(String(36), nullable=False, default="", comment="Created by")
    updated_by = Column(String(36), nullable=False, default="", comment="Updated by")


# table to save profile item value
# only for option type


class ProfileItemValue(db.Model):
    __tablename__ = "profile_item_value"
    id = Column(BIGINT, primary_key=True, autoincrement=True, comment="Unique ID")
    profile_id = Column(String(36), nullable=False, comment="Profile ID", index=True)
    profile_item_id = Column(
        String(36), nullable=False, comment="Profile item ID", index=True
    )
    profile_value = Column(Text, nullable=False, comment="Profile value")
    profile_value_index = Column(
        Integer, nullable=False, default=0, comment="Profile value index"
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
        Integer, nullable=False, default=0, comment="0 for deleted, 1 for active"
    )
    created_by = Column(String(36), nullable=False, default="", comment="Created by")
    updated_by = Column(String(36), nullable=False, default="", comment="Updated by")


# table to save profile item i18n


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
