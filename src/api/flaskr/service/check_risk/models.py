from ...dao import db
from sqlalchemy import (
    Column,
    String,
    Integer,
    TIMESTAMP,
    Text,
)
from sqlalchemy import BigInteger
from sqlalchemy.sql import func


class RiskControlResult(db.Model):
    __tablename__ = "risk_control_result"

    id = Column(BigInteger, primary_key=True, comment="Unique ID", autoincrement=True)
    chat_id = Column(String(36), nullable=False, default="", comment="Chat UUID")
    user_id = Column(String(36), nullable=False, default="", comment="User UUID")
    text = Column(Text, nullable=False, comment="Text")
    check_vendor = Column(
        String(255), nullable=False, default="", comment="Check vendor"
    )
    check_result = Column(Integer, nullable=False, default=0, comment="Check result")
    check_resp = Column(Text, nullable=False, comment="Check response")
    is_pass = Column(Integer, nullable=False, default=0, comment="Is pass")
    check_strategy = Column(
        String(30), nullable=False, default="", comment="Check strategy"
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

    def __init__(
        self,
        chat_id,
        user_id,
        text,
        check_vendor,
        check_result,
        check_resp,
        is_pass,
        check_strategy,
    ):
        self.chat_id = chat_id
        self.user_id = user_id
        self.text = text
        self.check_vendor = check_vendor
        self.check_result = check_result
        self.check_resp = check_resp
        self.is_pass = is_pass
        self.check_strategy = check_strategy
