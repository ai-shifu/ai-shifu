from sqlalchemy import Column, String, Integer, TIMESTAMP, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.sql import func
from pymilvus import MilvusClient, DataType

from ...common.config import get_config
from ...dao import db, milvus_client

default_embedding_model = get_config("DEFAULT_EMBEDDING_MODEL")
default_embedding_model_dim = get_config("DEFAULT_EMBEDDING_MODEL_DIM")


class KnowledgeBase(db.Model):
    __tablename__ = "knowledge_base"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    kb_id = Column(
        String(36),
        nullable=False,
        default="",
        comment="Knowledge Base ID",
        index=True,
    )
    kb_name = Column(
        String(255), nullable=False, default="", comment="Knowledge Base name"
    )
    kb_description = Column(
        Text, nullable=True, comment="Knowledge Base description", default=""
    )
    embedding_model = Column(
        String(255),
        nullable=False,
        default=default_embedding_model,
        comment="Embedding Model name",
    )
    dim = Column(
        Integer,
        nullable=False,
        default=default_embedding_model_dim,
        comment="VectorDB dim",
    )
    tag_ids = Column(
        Text,
        nullable=True,
        default=None,
        comment="Knowledge Base tags, separated by ','",
    )
    course_ids = Column(
        Text,
        nullable=True,
        default=None,
        comment="Course UUIDs, separated by ','",
    )
    meta_data = Column(Text, nullable=True, comment="Meta Data", default="{}")
    extra_data = Column(Text, nullable=True, comment="Extra Data", default="{}")
    created_user_id = Column(
        String(36), nullable=True, default="", comment="created user ID"
    )
    updated_user_id = Column(
        String(36), nullable=True, default="", comment="updated user ID"
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


def kb_schema(dim: int):
    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field(
        field_name="id", datatype=DataType.VARCHAR, max_length=128, is_primary=True
    )
    schema.add_field(field_name="document_id", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="index", datatype=DataType.INT32)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field(field_name="lesson_id", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(
        field_name="document_tag", datatype=DataType.VARCHAR, max_length=64
    )
    schema.add_field(
        field_name="meta_data", datatype=DataType.VARCHAR, max_length=65535
    )
    schema.add_field(
        field_name="create_user", datatype=DataType.VARCHAR, max_length=128
    )
    schema.add_field(field_name="create_time", datatype=DataType.VARCHAR, max_length=64)

    schema.add_field(
        field_name="update_user", datatype=DataType.VARCHAR, max_length=128
    )
    schema.add_field(field_name="update_time", datatype=DataType.VARCHAR, max_length=64)
    return schema


def kb_index_params():
    index_params = milvus_client.prepare_index_params()
    index_params.add_index(field_name="id", index_type="AUTOINDEX")
    index_params.add_index(
        field_name="vector", index_type="AUTOINDEX", metric_type="COSINE"
    )
    return index_params
