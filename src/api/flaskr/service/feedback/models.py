from ...dao import db
from sqlalchemy import (
    Column,
    String,
    TIMESTAMP,
)
from sqlalchemy import BigInteger
from sqlalchemy.sql import func


class FeedBack(db.Model):
    __tablename__ = "user_feedback"

    id = Column(BigInteger, primary_key=True, comment="Unique ID", autoincrement=True)
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    feedback = Column(String(300), nullable=False, comment="Feedback")
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

    def __init__(self, user_id, feedback):
        self.user_id = user_id
        self.feedback = feedback
