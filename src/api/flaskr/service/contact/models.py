
from ...dao import db
from sqlalchemy import Column, String, Integer,DateTime,Boolean, TIMESTAMP, Text, Index, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base


class Contact(db.Model):
    __tablename__ = 'contact'

    id = Column(BIGINT, primary_key=True, comment='Unique ID', autoincrement=True)
    contact_id = Column(String(36), nullable=False, default='', comment='Contact UUID')
    name = Column(String(255), nullable=False, default='', comment='Name')
    email = Column(String(255), nullable=False, default='', comment='Email')
    mobile = Column(String(20), nullable=False, default='', comment='Mobile')
    telephone = Column(String(20), nullable=False, default='', comment='Telephone')
    position = Column(String(255), nullable=False, default='', comment='Position')
    company = Column(String(255), nullable=False, default='', comment='Company')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')
    user_id = Column(String(36), nullable=False, default='', comment='User UUID')

    def __init__(self,user_id, contact_id, name, email, mobile, telephone, position, company):
        self.user_id = user_id
        self.contact_id = contact_id
        self.name = name
        self.email = email
        self.mobile = mobile
        self.telephone = telephone
        self.position = position
        self.company = company
