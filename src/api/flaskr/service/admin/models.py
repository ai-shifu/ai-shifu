from sqlalchemy import Column, String, Integer, TIMESTAMP, Text, Index, text,Date
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from ...dao import db

class AdminUser(db.Model):
    __tablename__ = 'admin_info'
    id = Column(BIGINT, primary_key=True, comment='Unique ID', autoincrement=True)
    user_id = Column(String(36), nullable=False, default='', comment='User UUID')
    username = Column(String(255), nullable=False, default='', comment='Login username')
    name = Column(String(255), nullable=False, default='', comment='User real name')
    password_hash = Column(String(255), nullable=False, default='', comment='Hashed password')
    email = Column(String(255), nullable=False, default='', comment='Email')
    mobile = Column(String(20), nullable=False, default='', comment='Mobile')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')
    default_model = Column(String(255), nullable=False, default='gpt-3.5-turbo-0613', comment='Default model')
    user_state= Column(Integer, nullable=True, default= 0, comment='User_state')
    user_sex = Column(Integer, nullable=True, default=0, comment='user sex')   
    user_birth =Column(Date,nullable=True,default='1984-1-1', comment='user birth')
    user_avatar = Column(String(255), nullable=True, default='', comment='user avatar')
    def __init__(self, user_id, username="", name="", password_hash="", email="", mobile="",default_model="gpt-3.5-turbo-0613",user_state=0):
        self.user_id = user_id
        self.username = username
        self.name = name
        self.password_hash = password_hash
        self.email = email
        self.mobile = mobile
        self.default_model = default_model
        self.user_state = user_state
