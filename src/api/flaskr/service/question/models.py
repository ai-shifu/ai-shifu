from sqlalchemy import (
    Column,
    String,
    Integer,
    TIMESTAMP,
    Text,
)
from sqlalchemy import BigInteger
from sqlalchemy.sql import func
from ...dao import db


class SelectQuestion(db.Model):
    __tablename__ = "select_question"
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Unique ID")
    question_id = Column(String(36), index=True, nullable=False, comment="Question ID")
    script_id = Column(String(36), index=True, nullable=False, comment="Script ID")
    logscript_id = Column(
        String(36), index=True, nullable=False, comment="Logscript ID"
    )
    user_id = Column(String(36), index=True, nullable=False, comment="User ID")
    genration_model = Column(String(255), nullable=False, comment="Generation model")
    genration_prompt = Column(Text, nullable=False, comment="Generation prompt")
    question = Column(Text, nullable=False, comment="Question")
    options = Column(Text, nullable=False, comment="Options")
    correct_answer = Column(String(255), nullable=False, comment="Correct answer")
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
