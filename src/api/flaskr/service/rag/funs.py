import json
import uuid
import datetime
from typing import Optional

import oss2
import openai
import pytz
from flask import Flask, current_app

from .models import (
    kb_schema,
    kb_index_params,
)
from ...dao import milvus_client
from ...common.config import get_config
from ..common.models import raise_error, raise_error_with_args

bj_time = pytz.timezone("Asia/Shanghai")

# oss
# copy from ../user/user.py
endpoint = get_config("ALIBABA_CLOUD_OSS_ENDPOINT")
ALI_API_ID = get_config("ALIBABA_CLOUD_OSS_ACCESS_KEY_ID", None)
ALI_API_SECRET = get_config("ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET", None)
IMAGE_BASE_URL = get_config("ALIBABA_CLOUD_OSS_BASE_URL", None)
BUCKET_NAME = get_config("ALIBABA_CLOUD_OSS_BUCKET", None)
if not ALI_API_ID or not ALI_API_SECRET or ALI_API_ID == "" or ALI_API_SECRET == "":
    current_app.logger.warning(
        "ALIBABA_CLOUD_ACCESS_KEY_ID or ALIBABA_CLOUD_ACCESS_KEY_SECRET not configured"
    )
else:
    auth = oss2.Auth(ALI_API_ID, ALI_API_SECRET)
    bucket = oss2.Bucket(auth, endpoint, BUCKET_NAME)

# embedding_model openai_compatible_client
embedding_client = openai.Client(
    base_url=get_config("EMBEDDING_MODEL_BASE_URL"),
    api_key=get_config("EMBEDDING_MODEL_API_KEY"),
)


def get_kb_list(app: Flask):
    with app.app_context():
        return milvus_client.list_collections()


def kb_exist(kb_id: str):
    return milvus_client.has_collection(collection_name=kb_id)


def kb_create(
    app: Flask,
    kb_id: str,
    embedding_model: str,
    dim: int,
    kb_category_0: str,
    kb_category_1: str,
    kb_category_2: str,
):
    with app.app_context():
        if kb_exist(kb_id) is False:
            properties = {
                "embedding_model": embedding_model,
                "dim": dim,
                "kb_category_0": kb_category_0,
                "kb_category_1": kb_category_1,
                "kb_category_2": kb_category_2,
            }
            milvus_client.create_collection(
                collection_name=kb_id,
                schema=kb_schema(dim),
                index_params=kb_index_params(),
                properties=properties,
            )
            return "success"


def kb_drop(app: Flask, kb_id_list: list):
    with app.app_context():
        for kb_id in kb_id_list:
            if kb_exist(kb_id) is True:
                milvus_client.drop_collection(collection_name=kb_id)
                # break
        return "success"


def kb_look_fun(kb_id: str):
    if kb_exist(kb_id):
        return milvus_client.describe_collection(collection_name=kb_id)
    else:
        return None


def get_kb_properties(kb_id: str):
    return kb_look_fun(kb_id)["properties"]


def get_content_type(extension: str):
    if extension in ["txt", "md"]:
        return "text/plain"
    raise_error("FILE.FILE_TYPE_NOT_SUPPORT")


def oss_file_upload(app: Flask, upload_file):
    with app.app_context():
        # file_upload
        if (
            not ALI_API_ID
            or not ALI_API_SECRET
            or ALI_API_ID == ""
            or ALI_API_SECRET == ""
        ):
            raise_error_with_args(
                "API.ALIBABA_CLOUD_NOT_CONFIGURED",
                config_var="ALIBABA_CLOUD_OSS_ACCESS_KEY_ID,ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET",
            )
        file_id = str(uuid.uuid4()).replace("-", "")
        extension = upload_file.filename.rsplit(".", 1)[1].lower()
        file_key = f"{file_id}.{extension}"
        bucket.put_object(
            file_key,
            upload_file,
            headers={"Content-Type": get_content_type(extension)},
        )
        url = f"{IMAGE_BASE_URL}/{file_id}.{extension}"
        app.logger.info(f"url: {url}")
        return file_key


def file_parser(file_content, extension: str):
    if extension in ["txt", "md"]:
        return file_content.read().decode("utf-8")
    raise_error("FILE.FILE_TYPE_NOT_SUPPORT")


def text_spilt(
    text: str, split_separator: str, split_max_length: int, split_chunk_overlap: int
):
    if len(set(split_separator)) == 1 and "##" in split_separator:
        if not str(split_separator).startswith("\n"):
            split_separator = f"\n{split_separator}"
        if not str(split_separator).endswith(" "):
            split_separator = f"{split_separator} "
    return [x.strip() for x in str(text).split(split_separator) if x.strip() != ""]


def get_vector_list(text_list: list, embedding_model: str):
    return [
        x.embedding
        for x in embedding_client.embeddings.create(
            model=embedding_model, input=text_list
        ).data
    ]


def get_embedding_model(kb_id: str, embedding_model: str):
    if embedding_model is None:
        embedding_model = get_kb_properties(kb_id).get("embedding_model", None)
        if embedding_model is None:
            embedding_model = get_config("DEFAULT_EMBEDDING_MODEL")
    return embedding_model


def kb_file_upload(
    app: Flask,
    kb_id: str,
    file_key: str,
    split_separator: str,
    split_max_length: int,
    split_chunk_overlap: int,
    embedding_model: str,
):
    with app.app_context():
        embedding_model = get_embedding_model(kb_id, embedding_model)

        # file_parser
        extension = file_key.split(".")[-1]
        file_content = bucket.get_object(file_key)
        all_text = file_parser(file_content, extension)
        app.logger.info(f"all_text:\n{all_text}")

        # text_spilt
        all_text_list = text_spilt(
            all_text, split_separator, split_max_length, split_chunk_overlap
        )
        number = 0
        processing_batch_size = 32
        for text_list in [
            all_text_list[i: i + processing_batch_size]
            for i in range(0, len(all_text_list), processing_batch_size)
        ]:
            app.logger.info(f"text_list:\n{text_list}")

            # vector_list
            vector_list = get_vector_list(text_list, embedding_model)

            # milvus insert
            data = []
            doc_category_0 = ""
            doc_category_1 = ""
            doc_category_2 = ""
            create_user = ""
            update_user = ""
            meta_data = {}
            for text, vector in zip(text_list, vector_list):
                number += 1

                app.logger.info(f"text: {text}")
                app.logger.info(f"vector[:10]: {vector[:10]}")
                data.append(
                    {
                        "id": number,
                        "vector": vector,
                        "text": text,
                        "doc_category_0": doc_category_0,
                        "doc_category_1": doc_category_1,
                        "doc_category_2": doc_category_2,
                        "create_time": str(datetime.datetime.now(bj_time)),
                        "update_time": "",
                        "create_user": create_user,
                        "update_user": update_user,
                        "meta_data": json.dumps(meta_data),
                    }
                )
                # break

            milvus_client.insert(collection_name=kb_id, data=data)

            # break

        return "success"


def retrieval_fun(kb_id: str, query: str, embedding_model: Optional[str] = None):
    embedding_model = get_embedding_model(kb_id, embedding_model)
    return "\n\n".join(
        [
            x["entity"]["text"]
            for x in milvus_client.search(
                collection_name=kb_id,
                anns_field="vector",
                data=[
                    get_vector_list(text_list=[query], embedding_model=embedding_model)[
                        0
                    ]
                ],
                limit=3,
                search_params={"metric_type": "COSINE"},
                output_fields=["text"],
            )[0]
        ]
    )


def retrieval(
    app: Flask, kb_id: str, query: str, embedding_model: Optional[str] = None
):
    with app.app_context():
        return retrieval_fun(kb_id, query, embedding_model)
