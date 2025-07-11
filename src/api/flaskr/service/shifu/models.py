from sqlalchemy import (
    Column,
    String,
    Integer,
    TIMESTAMP,
    Decimal,
    Text,
    SmallInteger,
    DateTime,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db
from .consts import ASK_MODE_DEFAULT


class ResourceType:
    CHAPTER = 9001
    SECTION = 9002
    BLOCK = 9003


class FavoriteScenario(db.Model):
    __tablename__ = "scenario_favorite"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    scenario_id = Column(
        String(36), nullable=False, default="", comment="Scenario UUID"
    )
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    status = Column(Integer, nullable=False, default=0, comment="Status")
    created_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )


class ScenarioResource(db.Model):
    __tablename__ = "scenario_resource"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    resource_resource_id = Column(
        String(36), nullable=False, default="", comment="Resource UUID", index=True
    )
    scenario_id = Column(
        String(36), nullable=False, default="", comment="Scenario UUID", index=True
    )
    chapter_id = Column(
        String(36), nullable=False, default="", comment="Chapter UUID", index=True
    )
    resource_type = Column(Integer, nullable=False, default=0, comment="Resource type")
    resource_id = Column(
        String(36), nullable=False, default="", comment="Resource UUID", index=True
    )
    is_deleted = Column(Integer, nullable=False, default=0, comment="Is deleted")
    created_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )


class AiCourseAuth(db.Model):
    __tablename__ = "ai_course_auth"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    course_auth_id = Column(
        String(36),
        nullable=False,
        default="",
        comment="course_auth_id UUID",
        index=True,
    )
    course_id = Column(String(36), nullable=False, default="", comment="course_id UUID")
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    # 1 read 2 write 3 delete 4 publish
    auth_type = Column(String(255), nullable=False, default="[]", comment="auth_info")
    status = Column(Integer, nullable=False, default=0, comment="Status")
    created_at = Column(
        TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )


# draft shifu's model
class ShifuDraftShifu(db.Model):
    __tablename__ = "shifu_draft_shifus"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    bid = Column(
        String(32), nullable=False, index=True, default="", comment="Shifu business ID"
    )
    name = Column(String(100), nullable=False, default="", comment="Shifu name")
    keywords = Column(String(100), nullable=False, default="", comment="Shifu keywords")
    description = Column(
        String(500), nullable=False, default="", comment="Shifu description"
    )
    avatar_res_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Shifu avatar's resource business ID",
    )
    llm = Column(String(100), nullable=False, default="", comment="Specified LLM model")
    llm_temperature = Column(
        Decimal(10, 2),
        nullable=False,
        default=0,
        comment="Specified temperature for the LLM model",
    )
    llm_system_prompt = Column(
        Text,
        nullable=False,
        default="",
        comment="Specified system prompt for the LLM model",
    )
    ask_enabled_status = Column(
        SmallInteger,
        nullable=False,
        default=ASK_MODE_DEFAULT,
        comment="Enable ask agent or not. 5101 for default to system setting, 5102 for disable, 5103 for enable",
    )
    ask_llm = Column(
        String(100),
        nullable=False,
        default="",
        comment="Specified LLM model for ask agent",
    )
    ask_llm_temperature = Column(
        Decimal(10, 2),
        nullable=False,
        default=0.0,
        comment="Specified LLM temperature for ask agent",
    )
    ask_llm_system_prompt = Column(
        Text,
        nullable=False,
        default="",
        comment="Specified system prompt for ask agent",
    )
    price = Column(Decimal(10, 2), nullable=False, default=0, comment="Shifu price")
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Shifu status: 6101: history, 6102: draft",
    )
    version = Column(
        Integer, nullable=False, index=True, default=0, comment="Shifu version"
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deleted or not. 0 for false, 1 for true",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Created timestamp"
    )
    created_user_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Creation user bid"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last updated timestamp",
        onupdate=func.now(),
    )
    updated_by_user_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Business ID of the user who last updated this Shifu",
    )


class ShifuDraftOutline(db.Model):
    __tablename__ = "shifu_draft_outlines"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    bid = Column(
        String(32), nullable=False, index=True, default="", comment="Item business ID"
    )
    shifu_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Shifu business ID"
    )
    name = Column(String(100), nullable=False, default="", comment="Shifu outline name")
    parent_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="The Business ID of parent outline",
    )
    position = Column(
        String(10),
        nullable=False,
        index=True,
        default="",
        comment="Outline position",
    )
    pre_outline_bids = Column(
        String(500),
        nullable=False,
        default="",
        comment="Outline pre outline bids",
    )
    llm = Column(String(100), nullable=False, default="", comment="Outline llm model")
    llm_temperature = Column(
        Decimal(10, 2),
        nullable=False,
        default=0,
        comment="Outline llm temperature",
    )
    llm_system_prompt = Column(
        Text, nullable=False, default="", comment="Outline llm system prompt"
    )
    ask_enabled_status = Column(
        SmallInteger,
        nullable=False,
        default=ASK_MODE_DEFAULT,
        comment="Shifu outline ask enabled status, 5101: default, 5102: disable, 5103: enable",
    )
    ask_llm = Column(
        String(100), nullable=False, default="", comment="Shifu outline ask llm model"
    )
    ask_llm_temperature = Column(
        Decimal(10, 2),
        nullable=False,
        default=0.0,
        comment="Shifu outline ask llm temperature",
    )
    ask_llm_system_prompt = Column(
        Text, nullable=False, default="", comment="Outline ask llm system prompt"
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Outline status: 6101: history, 6102: draft",
    )
    version = Column(
        Integer, nullable=False, index=True, default=0, comment="Outline version"
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="deleted status: 0: not deleted, 1: deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    created_user_bid = Column(
        String(32), nullable=False, default="", comment="Creation user bid"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Update time",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32), nullable=False, default="", comment="Update user bid"
    )


class ShifuDraftBlock(db.Model):
    __tablename__ = "shifu_draft_blocks"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    bid = Column(
        String(32), nullable=False, index=True, default="", comment="Block bid"
    )
    shifu_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Shifu bid"
    )
    outline_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Outline bid"
    )
    type = Column(SmallInteger, nullable=False, default=0, comment="Block type")
    position = Column(
        SmallInteger,
        nullable=False,
        index=True,
        default=0,
        comment="Shifu block position",
    )
    variable_bids = Column(
        String(500), nullable=False, default="", comment="Block variable bids"
    )
    resource_bids = Column(
        String(500), nullable=False, default="", comment="Block resource bids"
    )
    content = Column(Text, nullable=False, default="", comment="Shifu block content")
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Block status: 6101: history, 6102: draft",
    )
    version = Column(
        Integer, nullable=False, index=True, default=0, comment="Block version"
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="deleted status: 0: not deleted, 1: deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    created_user_bid = Column(
        String(32), nullable=False, default="", comment="Creation user bid"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Update time",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Update user bid",
    )


class ShifuDraftHistory(db.Model):
    __tablename__ = "shifu_draft_histories"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    bid = Column(
        String(32), nullable=False, index=True, default="", comment="Draft bid"
    )
    shifu_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Shifu bid"
    )
    draft_content = Column(Text, nullable=False, default="", comment="Draft content")
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )


# published shifu's model
class ShifuPublishedShifu(db.Model):
    __tablename__ = "shifu_published_shifus"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    shifu_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Shifu bid"
    )
    name = Column(String(100), nullable=False, default="", comment="Shifu name")
    keywords = Column(String(100), nullable=False, default="", comment="Shifu keywords")
    description = Column(
        String(500), nullable=False, default="", comment="Shifu description"
    )
    avatar_res_bid = Column(
        String(32), nullable=False, default="", comment="Shifu avatar resource bid"
    )
    llm = Column(String(100), nullable=False, default="", comment="Shifu llm model")
    llm_temperature = Column(
        Decimal(10, 2), nullable=False, default=0, comment="Shifu llm temperature"
    )
    llm_system_prompt = Column(
        Text, nullable=False, default="", comment="Shifu llm system prompt"
    )
    ask_enabled_status = Column(
        SmallInteger,
        nullable=False,
        default=ASK_MODE_DEFAULT,
        comment="Shifu ask enabled status, 5101: default, 5102: disable, 5103: enable",
    )
    ask_llm = Column(
        String(100), nullable=False, default="", comment="Shifu ask llm model"
    )
    ask_llm_temperature = Column(
        Decimal(10, 2), nullable=False, default=0.0, comment="Shifu ask llm temperature"
    )
    ask_llm_system_prompt = Column(
        Text, nullable=False, default="", comment="Shifu ask llm system prompt"
    )
    price = Column(Decimal(10, 2), nullable=False, default=0, comment="Shifu price")
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Shifu status: 6101: history, 6103: published",
    )
    version = Column(Integer, nullable=False, default=0, comment="Shifu version")
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="deleted status: 0: not deleted, 1: deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Update time",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32), nullable=False, default="", comment="Update user bid"
    )


class ShifuPublishedOutline(db.Model):
    __tablename__ = "shifu_published_outlines"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    outline_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Outline bid"
    )
    shifu_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Shifu bid"
    )
    name = Column(String(100), nullable=False, default="", comment="Shifu outline name")
    parent_bid = Column(
        String(32), nullable=False, default="", comment="Outline parent bid"
    )
    position = Column(
        String(10), nullable=False, default="", comment="Outline position"
    )
    pre_outline_bids = Column(
        String(500),
        nullable=False,
        default="",
        comment="Outline pre outline bids",
    )
    llm = Column(String(100), nullable=False, default="", comment="Outline llm model")
    llm_temperature = Column(
        Decimal(10, 2),
        nullable=False,
        default=0,
        comment="Shifu outline llm temperature",
    )
    llm_system_prompt = Column(
        Text, nullable=False, default="", comment="Shifu outline llm system prompt"
    )
    ask_enabled_status = Column(
        SmallInteger,
        nullable=False,
        default=ASK_MODE_DEFAULT,
        comment="Shifu outline ask enabled status, 5101: default, 5102: disable, 5103: enable",
    )
    ask_llm = Column(
        String(100), nullable=False, default="", comment="Shifu outline ask llm model"
    )
    ask_llm_temperature = Column(
        Decimal(10, 2),
        nullable=False,
        default=0.0,
        comment="Shifu outline ask llm temperature",
    )
    ask_llm_system_prompt = Column(
        Text, nullable=False, default="", comment="Shifu outline ask llm system prompt"
    )
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Outline status: 6101: history, 6103: published",
    )
    version = Column(Integer, nullable=False, default=0, comment="Outline version")
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="deleted status: 0: not deleted, 1: deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Update time",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32), nullable=False, default="", comment="Update user bid"
    )


class ShifuPublishedBlock(db.Model):
    __tablename__ = "shifu_published_blocks"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    block_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Block bid"
    )
    shifu_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Shifu bid"
    )
    outline_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Outline bid"
    )
    type = Column(SmallInteger, nullable=False, default=0, comment="Block type")
    position = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Block position",
    )
    variable_bids = Column(
        String(500), nullable=False, default="", comment="Block variable bids"
    )
    resource_bids = Column(
        String(500), nullable=False, default="", comment="Block resource bids"
    )
    content = Column(Text, nullable=False, default="", comment="Block content")
    status = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Block status: 6101: history, 6103: published",
    )
    version = Column(Integer, nullable=False, default=0, comment="Block version")
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="deleted status: 0: not deleted, 1: deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Update time",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32), nullable=False, default="", comment="Update user bid"
    )


class ShifuHistory(db.Model):
    __tablename__ = "shifu_histories"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    shifu_bid = Column(
        String(32), nullable=False, index=True, default="", comment="Shifu bid"
    )
    content = Column(Text, nullable=False, default="", comment="Shifu content")
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation time"
    )
    created_user_bid = Column(
        String(32), nullable=False, default="", comment="Creation user bid"
    )
