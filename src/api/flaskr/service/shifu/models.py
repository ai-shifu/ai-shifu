from sqlalchemy import (
    Column,
    String,
    Integer,
    TIMESTAMP,
    DECIMAL,
    Text,
    SmallInteger,
    DateTime,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from ...dao import db
from .consts import ASK_MODE_DEFAULT
from flaskr.util.compare import compare_decimal


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
    shifu_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Shifu business identifier",
    )
    title = Column(String(100), nullable=False, default="", comment="Shifu title")
    keywords = Column(
        String(100), nullable=False, default="", comment="Associated keywords"
    )
    description = Column(
        String(500), nullable=False, default="", comment="Shifu description"
    )
    avatar_res_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Avatar resource business identifier",
    )
    llm = Column(String(100), nullable=False, default="", comment="LLM model name")
    llm_temperature = Column(
        DECIMAL(10, 2),
        nullable=False,
        default=0,
        comment="LLM temperature parameter",
    )
    llm_system_prompt = Column(
        Text,
        nullable=False,
        default="",
        comment="LLM system prompt",
    )
    ask_enabled_status = Column(
        SmallInteger,
        nullable=False,
        default=ASK_MODE_DEFAULT,
        comment="Ask agent status: 5101=default, 5102=disabled, 5103=enabled",
    )
    ask_llm = Column(
        String(100),
        nullable=False,
        default="",
        comment="Ask agent LLM model",
    )
    ask_llm_temperature = Column(
        DECIMAL(10, 2),
        nullable=False,
        default=0.0,
        comment="Ask agent LLM temperature",
    )
    ask_llm_system_prompt = Column(
        Text,
        nullable=False,
        default="",
        comment="Ask agent LLM system prompt",
    )
    price = Column(DECIMAL(10, 2), nullable=False, default=0, comment="Shifu price")
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )
    created_user_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )
    updated_by_user_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Last updater user business identifier",
    )

    def clone(self):
        return ShifuDraftShifu(
            shifu_bid=self.shifu_bid,
            title=self.title,
            keywords=self.keywords,
            description=self.description,
            avatar_res_bid=self.avatar_res_bid,
            llm=self.llm,
            llm_temperature=self.llm_temperature,
            llm_system_prompt=self.llm_system_prompt,
            ask_enabled_status=self.ask_enabled_status,
            ask_llm=self.ask_llm,
            ask_llm_temperature=self.ask_llm_temperature,
            ask_llm_system_prompt=self.ask_llm_system_prompt,
            price=self.price,
            deleted=self.deleted,
            created_at=self.created_at,
            created_user_bid=self.created_user_bid,
            updated_at=self.updated_at,
            updated_by_user_bid=self.updated_by_user_bid,
        )

    def eq(self, other):
        return (
            self.shifu_bid == other.shifu_bid
            and self.title == other.title
            and self.keywords == other.keywords
            and self.description == other.description
            and self.avatar_res_bid == other.avatar_res_bid
            and self.llm == other.llm
            and compare_decimal(self.llm_temperature, other.llm_temperature)
            and self.llm_system_prompt == other.llm_system_prompt
            and self.ask_enabled_status == other.ask_enabled_status
            and self.ask_llm == other.ask_llm
            and compare_decimal(self.ask_llm_temperature, other.ask_llm_temperature)
            and self.ask_llm_system_prompt == other.ask_llm_system_prompt
            and compare_decimal(self.price, other.price)
        )

    def get_str_to_check(self):
        return f"{self.title} {self.keywords} {self.description} {self.llm_system_prompt} {self.ask_llm_system_prompt}"


class ShifuDraftOutlineItem(db.Model):
    __tablename__ = "shifu_draft_outline_items"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    outline_item_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Outline item business identifier",
    )
    shifu_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Shifu business identifier",
    )
    title = Column(
        String(100),
        nullable=False,
        default="",
        comment="Outline item title",
    )
    parent_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Parent outline item business identifier",
    )
    position = Column(
        String(10),
        nullable=False,
        index=True,
        default="",
        comment="Position in outline",
    )
    prerequisite_item_bids = Column(
        String(500),
        nullable=False,
        default="",
        comment="Prerequisite outline item business identifiers",
    )
    llm = Column(String(100), nullable=False, default="", comment="LLM model name")
    llm_temperature = Column(
        DECIMAL(10, 2),
        nullable=False,
        default=0,
        comment="LLM temperature parameter",
    )
    llm_system_prompt = Column(
        Text, nullable=False, default="", comment="LLM system prompt"
    )
    ask_enabled_status = Column(
        SmallInteger,
        nullable=False,
        default=ASK_MODE_DEFAULT,
        comment="Ask agent status: 5101=default, 5102=disabled, 5103=enabled",
    )
    ask_llm = Column(
        String(100), nullable=False, default="", comment="Ask agent LLM model"
    )
    ask_llm_temperature = Column(
        DECIMAL(10, 2),
        nullable=False,
        default=0.0,
        comment="Ask mode LLM temperature",
    )
    ask_llm_system_prompt = Column(
        Text, nullable=False, default="", comment="Ask mode LLM system prompt"
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )
    created_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Last updater user business identifier",
    )

    def clone(self):
        return ShifuDraftOutlineItem(
            outline_item_bid=self.outline_item_bid,
            shifu_bid=self.shifu_bid,
            title=self.title,
            parent_bid=self.parent_bid,
            position=self.position,
            prerequisite_item_bids=self.prerequisite_item_bids,
            llm=self.llm,
            llm_temperature=self.llm_temperature,
            llm_system_prompt=self.llm_system_prompt,
            ask_enabled_status=self.ask_enabled_status,
            ask_llm=self.ask_llm,
            ask_llm_temperature=self.ask_llm_temperature,
            ask_llm_system_prompt=self.ask_llm_system_prompt,
            deleted=self.deleted,
            created_at=self.created_at,
            created_user_bid=self.created_user_bid,
            updated_at=self.updated_at,
            updated_user_bid=self.updated_user_bid,
        )

    def eq(self, other):
        return (
            self.outline_item_bid == other.outline_item_bid
            and self.shifu_bid == other.shifu_bid
            and self.title == other.title
            and self.parent_bid == other.parent_bid
            and self.position == other.position
            and self.prerequisite_item_bids == other.prerequisite_item_bids
            and self.llm == other.llm
            and compare_decimal(self.llm_temperature, other.llm_temperature)
            and self.llm_system_prompt == other.llm_system_prompt
            and self.ask_enabled_status == other.ask_enabled_status
            and self.ask_llm == other.ask_llm
            and compare_decimal(self.ask_llm_temperature, other.ask_llm_temperature)
            and self.ask_llm_system_prompt == other.ask_llm_system_prompt
        )

    def get_str_to_check(self):
        return f"{self.title} {self.llm_system_prompt} {self.ask_llm_system_prompt}"


class ShifuDraftBlock(db.Model):
    __tablename__ = "shifu_draft_blocks"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    block_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Block business identifier",
    )
    shifu_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Shifu business identifier",
    )
    outline_item_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Outline item business identifier",
    )
    type = Column(SmallInteger, nullable=False, default=0, comment="Block type")
    position = Column(
        SmallInteger,
        nullable=False,
        index=True,
        default=0,
        comment="Block position within outline",
    )
    variable_bids = Column(
        String(500),
        nullable=False,
        default="",
        comment="Variable business identifiers used in block",
    )
    resource_bids = Column(
        String(500),
        nullable=False,
        default="",
        comment="Resource business identifiers used in block",
    )
    content = Column(Text, nullable=False, default="", comment="Block content")
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )
    created_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Last updater user business identifier",
    )

    def eq(self, other):
        return (
            self.block_bid == other.block_bid
            and self.shifu_bid == other.shifu_bid
            and self.outline_item_bid == other.outline_item_bid
            and self.type == other.type
            and self.position == other.position
            and self.variable_bids == other.variable_bids
            and self.resource_bids == other.resource_bids
            and self.content == other.content
        )

    def get_str_to_check(self):
        return f"{self.content}"

    def clone(self):
        return ShifuDraftBlock(
            block_bid=self.block_bid,
            shifu_bid=self.shifu_bid,
            outline_item_bid=self.outline_item_bid,
            type=self.type,
            position=self.position,
            variable_bids=self.variable_bids,
            resource_bids=self.resource_bids,
            content=self.content,
        )


class ShifuLogDraftStruct(db.Model):
    __tablename__ = "shifu_log_draft_structs"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    struct_bid = Column(
        String(32),
        nullable=False,
        index=True,
        unique=True,
        default="",
        comment="Content business identifier",
    )
    shifu_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Shifu business identifier",
    )
    struct = Column(
        Text, nullable=False, default="", comment="JSON serialized shifu struct"
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )
    created_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Last updater user business identifier",
    )


# published shifu's model
class ShifuPublishedShifu(db.Model):
    __tablename__ = "shifu_published_shifus"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    shifu_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Shifu business identifier",
    )
    title = Column(String(100), nullable=False, default="", comment="Shifu title")
    keywords = Column(
        String(100), nullable=False, default="", comment="Associated keywords"
    )
    description = Column(
        String(500), nullable=False, default="", comment="Shifu description"
    )
    avatar_res_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Avatar resource business identifier",
    )
    llm = Column(String(100), nullable=False, default="", comment="LLM model name")
    llm_temperature = Column(
        DECIMAL(10, 2), nullable=False, default=0, comment="LLM temperature parameter"
    )
    llm_system_prompt = Column(
        Text, nullable=False, default="", comment="LLM system prompt"
    )
    ask_enabled_status = Column(
        SmallInteger,
        nullable=False,
        default=ASK_MODE_DEFAULT,
        comment="Ask agent status: 5101=default, 5102=disabled, 5103=enabled",
    )
    ask_llm = Column(
        String(100), nullable=False, default="", comment="Ask agent LLM model"
    )
    ask_llm_temperature = Column(
        DECIMAL(10, 2), nullable=False, default=0.0, comment="Ask agent LLM temperature"
    )
    ask_llm_system_prompt = Column(
        Text, nullable=False, default="", comment="Ask agent LLM system prompt"
    )
    price = Column(DECIMAL(10, 2), nullable=False, default=0, comment="Shifu price")
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )
    created_user_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Last updater user business identifier",
    )


class ShifuPublishedOutlineItem(db.Model):
    __tablename__ = "shifu_published_outline_items"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    outline_item_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Outline item business identifier",
    )
    shifu_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Shifu business identifier",
    )
    title = Column(
        String(100), nullable=False, default="", comment="Outline item title"
    )
    type = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Outline item type: 9001=chapter, 9002=section, 9003=block",
    )
    hidden = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Hidden flag: 0=visible, 1=hidden",
    )
    parent_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Parent outline item business identifier",
    )
    position = Column(
        String(10), nullable=False, default="", comment="Outline position"
    )
    prerequisite_item_bids = Column(
        String(500),
        nullable=False,
        default="",
        comment="Prerequisite outline item business identifiers",
    )
    llm = Column(String(100), nullable=False, default="", comment="LLM model name")
    llm_temperature = Column(
        DECIMAL(10, 2),
        nullable=False,
        default=0,
        comment="LLM temperature parameter",
    )
    llm_system_prompt = Column(
        Text, nullable=False, default="", comment="LLM system prompt"
    )
    ask_enabled_status = Column(
        SmallInteger,
        nullable=False,
        default=ASK_MODE_DEFAULT,
        comment="Ask agent status: 5101=default, 5102=disabled, 5103=enabled",
    )
    ask_llm = Column(
        String(100), nullable=False, default="", comment="Ask agent LLM model"
    )
    ask_llm_temperature = Column(
        DECIMAL(10, 2),
        nullable=False,
        default=0.0,
        comment="Ask agent LLM temperature",
    )
    ask_llm_system_prompt = Column(
        Text, nullable=False, default="", comment="Ask agent LLM system prompt"
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )
    created_user_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Last updater user business identifier",
    )


class ShifuPublishedBlock(db.Model):
    __tablename__ = "shifu_published_blocks"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    block_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Block business identifier",
    )
    shifu_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Shifu business identifier",
    )
    outline_item_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Outline item business identifier",
    )
    type = Column(SmallInteger, nullable=False, default=0, comment="Block type")
    position = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Block position within outline",
    )
    variable_bids = Column(
        String(500),
        nullable=False,
        default="",
        comment="Variable business identifiers used in block",
    )
    resource_bids = Column(
        String(500),
        nullable=False,
        default="",
        comment="Resource business identifiers used in block",
    )
    content = Column(Text, nullable=False, default="", comment="Block content")
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )
    created_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Last updater user business identifier",
    )


class ShifuLogPublishedStruct(db.Model):
    __tablename__ = "shifu_log_published_structs"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    struct_bid = Column(
        String(32),
        nullable=False,
        index=True,
        unique=True,
        default="",
        comment="Content business identifier",
    )
    shifu_bid = Column(
        String(32),
        nullable=False,
        index=True,
        default="",
        comment="Shifu business identifier",
    )
    struct = Column(
        Text,
        nullable=False,
        default="",
        comment="JSON serialized struct of published shifu",
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Deletion flag: 0=active, 1=deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=func.now(), comment="Creation timestamp"
    )
    created_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Creator user business identifier",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.now(),
        comment="Last update timestamp",
        onupdate=func.now(),
    )
    updated_user_bid = Column(
        String(32),
        nullable=False,
        default="",
        comment="Last updater user business identifier",
    )
