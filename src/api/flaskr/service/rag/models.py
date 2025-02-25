from pymilvus import MilvusClient, DataType

from ...dao import milvus_client


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
