import json
import uuid
import datetime
import itertools

# from typing import Optional

import oss2
import pytz
import openai
from sqlalchemy import or_
from flask import Flask, current_app

from .models import (
    KnowledgeBase,
    KnowledgeFile,
    KnowledgeChunk,
    kb_schema,
    kb_index_params,
)
from ..tag.models import Tag
from ...dao import db, milvus_client
from ...common.config import get_config
from ..common.models import raise_error, raise_error_with_args

bj_time = pytz.timezone("Asia/Shanghai")

# oss
# copy from ../user/user.py
endpoint = get_config("ALIBABA_CLOUD_OSS_ENDPOINT")
ALI_API_ID = get_config("ALIBABA_CLOUD_OSS_ACCESS_KEY_ID")
ALI_API_SECRET = get_config("ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET")
IMAGE_BASE_URL = get_config("ALIBABA_CLOUD_OSS_BASE_URL")
BUCKET_NAME = get_config("ALIBABA_CLOUD_OSS_BUCKET")
if not ALI_API_ID or not ALI_API_SECRET:
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


def get_datetime_now_str():
    return str(datetime.datetime.now(bj_time))


def get_kb_list(
    app: Flask,
    tag_id_list,
    course_id_list,
):
    with app.app_context():
        query = db.session.query(
            KnowledgeBase.kb_id,
            KnowledgeBase.kb_name,
            KnowledgeBase.tag_ids,
            KnowledgeBase.course_ids,
        )
        if course_id_list:
            query = query.filter(
                or_(
                    *[
                        KnowledgeBase.course_ids.like(f"%{course_id}%")
                        for course_id in course_id_list
                    ]
                )
            )
        if tag_id_list:
            query = query.filter(
                or_(
                    *[
                        KnowledgeBase.tag_ids.like(f"%{tag_id}%")
                        for tag_id in tag_id_list
                    ]
                )
            )
        kb_list = [
            {
                "kb_id": kb_id,
                "kb_name": kb_name,
                "tag_ids": tag_ids.split(",") if tag_ids is not None else [],
                "course_id": course_ids.split(",") if course_ids is not None else [],
            }
            for kb_id, kb_name, tag_ids, course_ids in query.all()
        ]
        app.logger.info(f"kb_list: {kb_list}")
        return kb_list


def kb_add(
    app: Flask,
    kb_name: str,
    kb_description: str,
    embedding_model: str,
    dim: int,
    tag_id_list: list,
    course_id_list: list,
    user_id: str,
):
    with app.app_context():
        kb_id = f"uuid{str(uuid.uuid4()).replace('-', '')}"
        app.logger.info(f"kb_id: {kb_id}")

        tag_ids = ",".join(tag_id_list) if tag_id_list else None
        course_ids = ",".join(course_id_list) if course_id_list else None

        if KnowledgeBase.query.filter_by(kb_name=kb_name).first():
            app.logger.error("kb_name already exists")
            return False
        if milvus_client is not None:
            raise_error("RAG.MILVUS_NOT_CONFIGURED")

        kb_item = KnowledgeBase(
            kb_id=kb_id,
            kb_name=kb_name,
            kb_description=kb_description,
            embedding_model=embedding_model,
            dim=dim,
            tag_ids=tag_ids,
            course_ids=course_ids,
            created_user_id=user_id,
        )
        db.session.add(kb_item)

        properties = {
            "dim": dim,
            "create_user": user_id,
            "create_time": get_datetime_now_str(),
        }
        milvus_client.create_collection(
            # collection name can only contain numbers, letters and underscores
            collection_name=kb_id,
            schema=kb_schema(dim),
            index_params=kb_index_params(),
            properties=properties,
        )

        db.session.commit()

        return kb_id


def kb_update(
    app: Flask,
    kb_id: str,
    kb_name: str,
    description: str,
    embedding_model: str,
    tag_id_list: list,
    course_id_list: list,
    user_id: str,
):
    with app.app_context():
        kb_item = KnowledgeBase.query.filter_by(kb_id=kb_id).first()
        if kb_item:
            if kb_name is not None:
                if KnowledgeBase.query.filter_by(kb_name=kb_name).first():
                    app.logger.error("kb_name already exists")
                    return False
                kb_item.kb_name = kb_name
            if description is not None:
                kb_item.kb_description = description
            if embedding_model is not None:
                kb_item.embedding_model = embedding_model
            if tag_id_list is not None:
                kb_item.tag_ids = ",".join(tag_id_list)
            if course_id_list is not None:
                kb_item.course_ids = ",".join(course_id_list)
            kb_item.updated_user_id = user_id
            db.session.commit()
            return True
        else:
            app.logger.error("kb_id is not found")
            return False


def milvus_kb_exist(kb_id: str):
    if milvus_client is None:
        raise_error("RAG.MILVUS_NOT_CONFIGURED")
    return milvus_client.has_collection(collection_name=kb_id)


def kb_query(app: Flask, kb_id: str):
    with app.app_context():
        if milvus_kb_exist(kb_id):
            kb_item = KnowledgeBase.query.filter_by(kb_id=kb_id).first()
            if kb_item:
                return {
                    "kb_id": kb_item.kb_id,
                    "kb_name": kb_item.kb_name,
                    "kb_description": kb_item.kb_description,
                    "embedding_model": kb_item.embedding_model,
                    "dim": kb_item.dim,
                    "tag_ids": (
                        kb_item.tag_ids.split(",")
                        if kb_item.tag_ids is not None
                        else []
                    ),
                    "course_ids": (
                        kb_item.course_ids.split(",")
                        if kb_item.course_ids is not None
                        else []
                    ),
                }


def kb_drop(app: Flask, kb_id_list: list):
    with app.app_context():
        if milvus_client is None:
            raise_error("RAG.MILVUS_NOT_CONFIGURED")
        for kb_id in kb_id_list:
            kb_item = KnowledgeBase.query.filter_by(kb_id=kb_id).first()
            if kb_item:
                db.session.delete(kb_item)
                if milvus_kb_exist(kb_id) is True:
                    milvus_client.drop_collection(collection_name=kb_id)
                db.session.commit()
            # break
        return True


def kb_tag_bind(
    app: Flask,
    kb_id: str,
    tag_id: str,
):
    with app.app_context():
        if milvus_client is None:
            raise_error("RAG.MILVUS_NOT_CONFIGURED")
        kb_item = KnowledgeBase.query.filter_by(kb_id=kb_id).first()
        if not kb_item:
            app.logger.error(f"KnowledgeBase with kb_id {kb_id} not found")
            return False

        if not Tag.query.filter_by(tag_id=tag_id).first():
            app.logger.error(f"Invalid tag_id: {tag_id}")
            return False

        tag_id_list = kb_item.tag_ids.split(",") if kb_item.tag_ids else []

        if tag_id in tag_id_list:
            app.logger.error(
                f"Tag {tag_id} is already bound to KnowledgeBase with kb_id {kb_id}"
            )
            return False

        tag_id_list.append(tag_id)

        kb_item.tag_ids = ",".join(tag_id_list)
        db.session.commit()

        return True


def kb_tag_unbind(
    app: Flask,
    kb_id: str,
    tag_id: str,
):
    with app.app_context():
        kb_item = KnowledgeBase.query.filter_by(kb_id=kb_id).first()
        if not kb_item:
            app.logger.error(f"KnowledgeBase with kb_id {kb_id} not found")
            return False

        if not Tag.query.filter_by(tag_id=tag_id).first():
            app.logger.error(f"Invalid tag_id: {tag_id}")
            return False

        if not kb_item.tag_ids:
            app.logger.error(f"KnowledgeBase with kb_id {kb_id} has no tags to unbind")
            return False

        tag_id_list = kb_item.tag_ids.split(",")

        if tag_id not in tag_id_list:
            app.logger.error(
                f"Tag {tag_id} not bound to KnowledgeBase with kb_id {kb_id}"
            )
            return False

        tag_id_list.remove(tag_id)

        kb_item.tag_ids = ",".join(tag_id_list) if tag_id_list else None
        db.session.commit()

        return True


def get_content_type(extension: str):
    if extension in ["txt", "md"]:
        return "text/plain"
    raise_error("FILE.FILE_TYPE_NOT_SUPPORT")


def oss_file_add(app: Flask, upload_file):
    with app.app_context():
        # file_upload
        if not ALI_API_ID or not ALI_API_SECRET:
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


def oss_file_drop(app: Flask, file_key_list):
    with app.app_context():
        if not ALI_API_ID or not ALI_API_SECRET:
            raise_error_with_args(
                "API.ALIBABA_CLOUD_NOT_CONFIGURED",
                config_var="ALIBABA_CLOUD_OSS_ACCESS_KEY_ID,ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET",
            )
        for file_key in file_key_list:
            bucket.delete_object(file_key)
            # break
        return True


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


def get_embedding_model(kb_id: str):
    embedding_model = get_config("DEFAULT_EMBEDDING_MODEL")
    return embedding_model


def pad_string(index: int, length: int = 4):
    return str(index).zfill(length)


def get_kb_file_list(
    app: Flask,
    kb_id: str,
):
    with app.app_context():
        file_list = KnowledgeFile.query.filter_by(kb_id=kb_id).all()
        return [
            {
                "file_id": x.file_id,
                "file_key": x.file_key,
                "file_name": x.file_name,
            }
            for x in file_list
        ]


def kb_file_add(
    app: Flask,
    kb_id: str,
    file_key: str,
    file_name: str,
    file_tag_id: str,
    split_separator: str,
    split_max_length: int,
    split_chunk_overlap: int,
    user_id: str,
):
    with app.app_context():
        if milvus_client is None:
            raise_error("RAG.MILVUS_NOT_CONFIGURED")
        file_id = str(uuid.uuid4()).replace("-", "")

        embedding_model = get_embedding_model(kb_id)

        # file_parser
        extension = file_key.split(".")[-1]
        file_content = bucket.get_object(file_key)
        all_text = file_parser(file_content, extension)
        app.logger.info(f"all_text:\n{all_text}")

        # text_spilt
        all_text_list = text_spilt(
            all_text, split_separator, split_max_length, split_chunk_overlap
        )

        file_meta_data = json.dumps({})
        file_extra_data = json.dumps({})
        file_item = KnowledgeFile(
            kb_id=kb_id,
            file_id=file_id,
            file_key=file_key,
            file_name=file_name,
            file_text=all_text,
            meta_data=file_meta_data,
            extra_data=file_extra_data,
            created_user_id=user_id,
        )
        db.session.add(file_item)

        index = 0
        processing_batch_size = 32
        for text_list in (
            list(itertools.islice(all_text_list, i, i + processing_batch_size))
            for i in range(0, len(all_text_list), processing_batch_size)
        ):
            app.logger.info(f"text_list:\n{text_list}")

            # vector_list
            vector_list = get_vector_list(text_list, embedding_model)

            # milvus insert
            data = []
            create_time = get_datetime_now_str()
            chunk_meta_data = json.dumps({})
            chunk_extra_data = json.dumps({})
            for text, vector in zip(text_list, vector_list):
                app.logger.info(f"text: {text}")
                app.logger.info(f"vector[:10]: {vector[:10]}")

                chunk_id = f'{file_id[:8]}-{str(index).zfill(8)}-{str(uuid.uuid4()).replace("-", "")}'

                chunk_item = KnowledgeChunk(
                    kb_id=kb_id,
                    file_id=file_id,
                    chunk_id=chunk_id,
                    chunk_index=index,
                    chunk_text=text,
                    chunk_vector=json.dumps(vector),
                    meta_data=chunk_meta_data,
                    extra_data=chunk_extra_data,
                    created_user_id=user_id,
                )
                db.session.add(chunk_item)

                data.append(
                    {
                        "id": chunk_id,
                        "knowledge_id": kb_id,
                        "file_tag_id": file_tag_id,
                        "file_id": file_id,
                        "index": index,
                        "text": text,
                        "vector": vector,
                        "create_time": create_time,
                        "update_time": "",
                        "create_user": user_id,
                        "update_user": "",
                        "meta_data": chunk_meta_data,
                        "extra_data": chunk_extra_data,
                    }
                )

                index += 1

                # break

            milvus_client.insert(collection_name=kb_id, data=data)

            # break

        db.session.commit()

        return "success"


def kb_file_query(
    app: Flask,
    kb_id: str,
    file_id: str,
):
    with app.app_context():
        file_item = KnowledgeFile.query.filter_by(kb_id=kb_id, file_id=file_id).first()
        if not file_item:
            raise_error("FILE.FILE_NOT_FOUND")
        file_key = file_item.file_key
        file_name = file_item.file_name
        file_text = file_item.file_text
        meta_data = file_item.meta_data
        extra_data = file_item.extra_data
        chunk_list = [
            {
                "chunk_id": x.chunk_id,
                "chunk_index": x.chunk_index,
                "chunk_text": x.chunk_text,
            }
            for x in KnowledgeChunk.query.filter_by(kb_id=kb_id, file_id=file_id).all()
        ]
        return {
            "file_id": file_id,
            "file_key": file_key,
            "file_name": file_name,
            "file_text": file_text,
            "meta_data": meta_data,
            "extra_data": extra_data,
            "chunk_list": chunk_list,
        }


def retrieval_fun(
    kb_id: str,
    query: str,
    my_filter: str,
    limit: int,
    output_fields: list,
):
    if milvus_client is not None:
        raise_error("RAG.MILVUS_NOT_CONFIGURED")
    embedding_model = get_embedding_model(kb_id)
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
                filter=my_filter,
                limit=limit,
                search_params={"metric_type": "COSINE"},
                output_fields=output_fields,
            )[0]
        ]
    )


def retrieval(
    app: Flask,
    kb_id: str,
    query: str,
    my_filter: str,
    limit: int,
    output_fields: list,
):
    with app.app_context():
        return retrieval_fun(kb_id, query, my_filter, limit, output_fields)
