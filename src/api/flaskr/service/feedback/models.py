"""Define persistence models for user feedback."""

from flaskr.dao import db
from flaskr.util.datetime import now_utc
from sqlalchemy import (
    TIMESTAMP,
    Column,
    String,
)
from sqlalchemy.dialects.mysql import BIGINT


class FeedBack(db.Model):
    """Persist submitted product feedback."""

    __tablename__ = "user_feedback"

    id = Column(BIGINT, primary_key=True, comment="Unique ID", autoincrement=True)
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    feedback = Column(String(300), nullable=False, comment="Feedback")
    created = Column(
        TIMESTAMP, nullable=False, default=now_utc, comment="Creation time"
    )
    updated = Column(
        TIMESTAMP,
        nullable=False,
        default=now_utc,
        onupdate=now_utc,
        comment="Update time",
    )

    def __init__(self, user_id, feedback) -> None:
        """Initialize a user feedback record."""
        self.user_id = user_id
        self.feedback = feedback
