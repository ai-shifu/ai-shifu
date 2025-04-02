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
        comment="Knowledge Base Tag IDs, separated by ','",
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


class KnowledgeFile(db.Model):
    __tablename__ = "knowledge_file"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    kb_id = Column(
        String(36),
        nullable=False,
        default="",
        comment="Knowledge Base ID",
        index=True,
    )
    file_tag_id = Column(
        Text,
        nullable=True,
        default=None,
        comment="File Tag ID",
    )
    file_id = Column(
        String(36),
        nullable=False,
        default="",
        comment="File ID",
        index=True,
    )
    file_key = Column(String(255), nullable=False, default="", comment="File oss key")
    file_name = Column(String(255), nullable=True, default="", comment="File name")
    file_text = Column(Text, nullable=True, comment="File text", default="")
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


class KnowledgeChunk(db.Model):
    __tablename__ = "knowledge_chunk"
    id = Column(BIGINT, primary_key=True, autoincrement=True)
    kb_id = Column(
        String(36),
        nullable=False,
        default="",
        comment="Knowledge Base ID",
        index=True,
    )
    file_id = Column(
        String(36),
        nullable=False,
        default="",
        comment="File ID",
        index=True,
    )
    chunk_id = Column(
        String(64),
        nullable=False,
        default="",
        comment="Chunk ID",
        index=True,
    )
    chunk_index = Column(
        Integer,
        nullable=True,
        default=-1,
        comment="Chunk index",
    )
    chunk_text = Column(Text, nullable=True, comment="Chunk text", default="")
    chunk_vector = Column(Text, nullable=True, comment="Chunk vector", default="[]")
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
    schema.add_field(
        field_name="knowledge_id", datatype=DataType.VARCHAR, max_length=64
    )
    schema.add_field(field_name="file_tag_id", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="file_id", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="index", datatype=DataType.INT32)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
    schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
    schema.add_field(
        field_name="meta_data", datatype=DataType.VARCHAR, max_length=65535
    )
    schema.add_field(
        field_name="extra_data", datatype=DataType.VARCHAR, max_length=65535
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
