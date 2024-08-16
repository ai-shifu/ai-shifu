from sqlalchemy import Column, String, Integer, TIMESTAMP, Text, Index, text,Date
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from ...dao import db


class User(db.Model):
    __tablename__ = 'user_info'

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



class UserConversion(db.Model):
    __tablename__ = 'user_conversion'

    id = Column(BIGINT, primary_key=True, autoincrement=True, comment='Unique ID')
    user_id = Column(String(36), nullable=False, default='', comment='User UUID')
    conversion_id = Column(String(36), nullable=False, default='', comment='Conversion UUID')
    conversion_source = Column(String(36), nullable=False, default=0, comment='Conversion type')
    conversion_status = Column(Integer, nullable=False, default=0, comment='Conversion state')
    conversion_uuid = Column(String(36), nullable=False, default='', comment='Conversion UUID')
    conversion_third_platform = Column(String(255), nullable=False, default='', comment='Conversion third platform')
    created = Column(TIMESTAMP, nullable=False, default=func.now(), comment='Creation time')
    updated = Column(TIMESTAMP, nullable=False, default=func.now(), onupdate=func.now(), comment='Update time')

    def __init__(self, user_id, conversion_id, conversion_source, conversion_status, conversion_uuid='', conversion_third_platform=''):
        self.user_id = user_id
        self.conversion_id = conversion_id
        self.conversion_source = conversion_source
        self.conversion_status = conversion_status
        self.conversion_uuid = conversion_uuid
        self.conversion_third_platform = conversion_third_platform
 