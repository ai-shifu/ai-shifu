"""Durable, deployment-scoped retake policies and operation ledger."""

from flaskr.dao import db
from flaskr.util.datetime import now_utc
from sqlalchemy import JSON, Column, DateTime, Index, Integer, String


class CourseRetakePolicy(db.Model):
    """A live service policy, deliberately independent from course drafts."""

    __tablename__ = "course_retake_policies"

    namespace = Column(String(32), primary_key=True)
    shifu_bid = Column(String(36), primary_key=True)
    lesson_limit = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)
    updated_at = Column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)


class LessonRetakeAttempt(db.Model):
    """An idempotent operation, not a counter reconstructed from analytics."""

    __tablename__ = "lesson_retake_attempts"
    __table_args__ = (
        Index(
            "idx_retake_balance",
            "namespace",
            "shifu_bid",
            "user_bid",
            "outline_bid",
            "state",
        ),
    )

    attempt_id = Column(String(64), primary_key=True)
    namespace = Column(String(32), nullable=False)
    shifu_bid = Column(String(36), nullable=False)
    user_bid = Column(String(36), nullable=False)
    outline_bid = Column(String(36), nullable=False)
    request_id = Column(String(36), nullable=False)
    state = Column(String(16), nullable=False)
    producer_id = Column(String(36), nullable=True)
    producer_finished_at = Column(DateTime, nullable=True)
    recovery_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now_utc)
    updated_at = Column(DateTime, nullable=False, default=now_utc, onupdate=now_utc)
