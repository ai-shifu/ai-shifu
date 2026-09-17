"""Persistence for agent lesson sessions.

One row per learner per lesson. The session itself is a JSON document produced by the engine: the
pydantic-ai message history, the learner's answers, whatever is still pending, and the memory the
lesson has gathered. None of it is queried as structured data, so it stays opaque here.

The two version columns are what make an old row safe to refuse. The engine's tools and events are
product code in this repository and will change, and a stored history that mentions a tool call the
current code no longer understands cannot be resumed. Rather than guess, the reader compares both
versions and tells the caller to start the lesson over.
"""

from typing import ClassVar

from flaskr.dao import db
from flaskr.util.datetime import now_utc
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.mysql import BIGINT

# Bumped whenever a change to the engine makes previously stored sessions unreadable -- a renamed
# tool, a changed argument, a different event shape. Rows that do not match are not resumed.
AGENT_SESSION_SCHEMA_VERSION = 1


class LearnAgentSession(db.Model):
    """One agent lesson session, stored as the engine serialized it."""

    __tablename__ = "learn_agent_sessions"
    __table_args__: ClassVar[tuple] = (
        Index(
            "idx_learn_agent_sessions_user_outline",
            "user_bid",
            "outline_item_bid",
        ),
        {"comment": "Agent lesson sessions"},
    )

    id = Column(BIGINT, primary_key=True, autoincrement=True)
    agent_session_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Agent session business identifier",
        index=True,
    )
    user_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="User business identifier",
        index=True,
    )
    shifu_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Shifu business identifier",
        index=True,
    )
    outline_item_bid = Column(
        String(36),
        nullable=False,
        default="",
        comment="Outline item business identifier",
        index=True,
    )
    session_data = Column(
        Text(length=4294967295),
        nullable=False,
        default="",
        comment="Engine session document as JSON",
    )
    schema_version = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Engine session schema version this row was written with",
    )
    pydantic_ai_version = Column(
        String(32),
        nullable=False,
        default="",
        comment="pydantic-ai version that produced the stored message history",
    )
    turn = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Turns taken so far in this session",
    )
    finished = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Whether the lesson reached its end",
    )
    deleted = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="Whether the row is deleted",
    )
    created_at = Column(
        DateTime, nullable=False, default=now_utc, comment="Creation time"
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=now_utc,
        onupdate=now_utc,
        comment="Update time",
    )
