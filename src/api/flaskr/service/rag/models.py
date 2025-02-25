from sqlalchemy.sql import func
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy import Column, String, Integer, TIMESTAMP, Date
from pymilvus import MilvusClient, DataType

from ...dao import db, milvus_client


# class TableTest(db.Model):
#     __tablename__ = "table_test"
#
#     id = Column(BIGINT, primary_key=True, comment="Unique ID", autoincrement=True)
#     user_id = Column(
#         String(36), nullable=False, index=True, default="", comment="User UUID"
#     )
#     username = Column(String(255), nullable=False, default="", comment="Login username")
#     name = Column(String(255), nullable=False, default="", comment="User real name")
#     password_hash = Column(
#         String(255), nullable=False, default="", comment="Hashed password"
#     )
#     email = Column(String(255), nullable=False, default="", comment="Email")
#     mobile = Column(
#         String(20), nullable=False, index=True, default="", comment="Mobile"
#     )
#     created = Column(
#         TIMESTAMP, nullable=False, default=func.now(), comment="Creation time"
#     )
#     updated = Column(
#         TIMESTAMP,
#         nullable=False,
#         onupdate=func.now(),
#         default=func.now(),
#         comment="Update time",
#     )
#     default_model = Column(
#         String(255),
#         nullable=False,
#         default="gpt-3.5-turbo-0613",
#         comment="Default model",
#     )
#     user_state = Column(Integer, nullable=True, default=0, comment="User_state")
#     user_sex = Column(Integer, nullable=True, default=0, comment="user sex")
#     user_birth = Column(Date, nullable=True, default="2003-1-1", comment="user birth")
#     user_avatar = Column(String(255), nullable=True, default="", comment="user avatar")
#     user_open_id = Column(
#         String(255), nullable=True, index=True, default="", comment="user open id"
#     )
#     user_unicon_id = Column(
#         String(255), nullable=True, index=True, default="", comment="user unicon id"
#     )
#     user_language = Column(
#         String(30), nullable=True, default="zh", comment="user language"
#     )
#
#     def __init__(
#             self,
#             user_id,
#             username="",
#             name="",
#             password_hash="",
#             email="",
#             mobile="",
#             default_model="gpt-3.5-turbo-0613",
#             user_state=0,
#             language="zh_CN",
#     ):
#         self.user_id = user_id
#         self.username = username
#         self.name = name
#         self.password_hash = password_hash
#         self.email = email
#         self.mobile = mobile
#         self.default_model = default_model
#         self.user_state = user_state
#         self.user_language = language


def kb_schema(dim: int):
    schema = MilvusClient.create_schema(
        auto_id=False,
        enable_dynamic_field=True,
    )
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
    schema.add_field(
        field_name="doc_category_0", datatype=DataType.VARCHAR, max_length=64
    )
    schema.add_field(
        field_name="doc_category_1", datatype=DataType.VARCHAR, max_length=64
    )
    schema.add_field(
        field_name="doc_category_2", datatype=DataType.VARCHAR, max_length=64
    )
    schema.add_field(field_name="create_time", datatype=DataType.VARCHAR, max_length=32)
    schema.add_field(field_name="update_time", datatype=DataType.VARCHAR, max_length=32)
    schema.add_field(
        field_name="create_user", datatype=DataType.VARCHAR, max_length=128
    )
    schema.add_field(
        field_name="update_user", datatype=DataType.VARCHAR, max_length=128
    )
    schema.add_field(
        field_name="meta_data", datatype=DataType.VARCHAR, max_length=65535
    )
    return schema


def kb_index_params():
    index_params = milvus_client.prepare_index_params()
    index_params.add_index(field_name="id", index_type="STL_SORT")
    index_params.add_index(
        field_name="vector", index_type="AUTOINDEX", metric_type="COSINE"
    )
    return index_params
