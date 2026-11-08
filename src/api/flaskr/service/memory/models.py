"""Persistence for course-scoped answer bindings."""

from typing import ClassVar

from flaskr.dao import db
from sqlalchemy import Column, String, Text


class CourseAnswerAlias(db.Model):
    """Map a learner's legacy binding to a question without copying its answer."""

    __tablename__ = "var_course_answer_aliases"
    __table_args__: ClassVar[dict[str, str]] = {
        "comment": "Course-scoped links from legacy answer bindings to question keys."
    }

    user_bid = Column(String(32), primary_key=True)
    shifu_bid = Column(String(32), primary_key=True)
    alias_digest = Column(String(64), primary_key=True)
    alias = Column(Text, nullable=False)
    question_key = Column(String(255), nullable=False)
