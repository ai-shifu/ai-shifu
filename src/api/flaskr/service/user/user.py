# user service
# author: yfge
#


import uuid
from flask import Flask, current_app

from ...common.config import get_config
from ..common.models import raise_error, raise_error_with_args

from .utils import generate_token
from ...service.common.dtos import USER_STATE_UNREGISTERED, UserToken
from ...service.user.models import UserConversion
from ...dao import db
from ...api.wechat import get_wechat_access_token
import oss2
from .repository import (
    build_user_info_from_aggregate,
    create_user_entity,
    ensure_user_aggregate,
    find_credential,
    get_user_entity_by_bid,
    load_user_aggregate,
    upsert_wechat_credentials,
    update_user_entity_fields,
)


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

# generate temp user for anonymous user
# author: yfge


def generate_temp_user(
    app: Flask, temp_id: str, user_source="web", wx_code=None, language="en-US"
) -> UserToken:
    with app.app_context():
        convert_user = UserConversion.query.filter(
            UserConversion.conversion_id == temp_id,
            UserConversion.conversion_source == user_source,
        ).first()
        wx_openid = ""
        wx_unionid = ""
        if wx_code:
            wx_data = get_wechat_access_token(app, wx_code)
            if wx_data:
                wx_openid = wx_data.get("openid", "")
                wx_unionid = wx_data.get("unionid", "")
        if not convert_user:
            if wx_openid != "":
                credential = find_credential(
                    provider_name="wechat", identifier=wx_openid
                )
                if credential:
                    aggregate = load_user_aggregate(credential.user_bid)
                    if aggregate:
                        return UserToken(
                            build_user_info_from_aggregate(aggregate),
                            token=generate_token(app, user_id=aggregate.user_bid),
                        )
            user_id = uuid.uuid4().hex
            new_convert_user = UserConversion(
                user_id=user_id,
                conversion_uuid=temp_id,
                conversion_id=temp_id,
                conversion_source=user_source,
                conversion_status=0,
            )
            db.session.add(new_convert_user)
            new_entity = create_user_entity(
                user_bid=user_id,
                identify=user_id,
                nickname="",
                language=language,
                state=USER_STATE_UNREGISTERED,
            )
            if wx_openid:
                upsert_wechat_credentials(
                    app,
                    user_bid=new_entity.user_bid,
                    open_id=wx_openid,
                    union_id=wx_unionid,
                    verified=True,
                )
            db.session.commit()
            aggregate = load_user_aggregate(user_id)
            if not aggregate:
                raise_error("USER.USER_NOT_FOUND")
            token = generate_token(app, user_id=user_id)
            return UserToken(build_user_info_from_aggregate(aggregate), token=token)
        else:
            if wx_openid != "":
                credential = find_credential(
                    provider_name="wechat", identifier=wx_openid
                )
                if credential:
                    aggregate = load_user_aggregate(credential.user_bid)
                    if aggregate:
                        return UserToken(
                            build_user_info_from_aggregate(aggregate),
                            token=generate_token(app, user_id=aggregate.user_bid),
                        )

            aggregate, _ = ensure_user_aggregate(app, user_bid=convert_user.user_id)
            if wx_openid:
                upsert_wechat_credentials(
                    app,
                    user_bid=aggregate.user_bid,
                    open_id=wx_openid,
                    union_id=wx_unionid,
                    verified=True,
                )
            db.session.commit()
            refreshed = load_user_aggregate(convert_user.user_id)
            if not refreshed:
                raise_error("USER.USER_NOT_FOUND")
            token = generate_token(app, user_id=refreshed.user_bid)
            return UserToken(build_user_info_from_aggregate(refreshed), token=token)


def update_user_open_id(app: Flask, user_id: str, wx_code: str) -> str:
    app.logger.info(f"update_user_open_id user_id: {user_id} wx_code: {wx_code}")
    with app.app_context():
        aggregate = load_user_aggregate(user_id)
        if not aggregate:
            app.logger.error("user not found")
            return ""

        wx_data = get_wechat_access_token(app, wx_code)
        if not wx_data:
            return ""

        wx_openid = wx_data.get("openid", "")
        wx_unionid = wx_data.get("unionid", "")
        if wx_openid and aggregate.wechat_open_id != wx_openid:
            upsert_wechat_credentials(
                app,
                user_bid=aggregate.user_bid,
                open_id=wx_openid,
                union_id=wx_unionid,
                verified=True,
            )
            db.session.commit()
            app.logger.info(
                "update_user_open_id user_id: %s wx_openid: %s",
                user_id,
                wx_openid,
            )
        return wx_openid


def get_content_type(filename):
    extension = filename.rsplit(".", 1)[1].lower()
    if extension in ["jpg", "jpeg"]:
        return "image/jpeg"
    elif extension == "png":
        return "image/png"
    elif extension == "gif":
        return "image/gif"
    raise_error("server.file.fileTypeNotSupport")


def upload_user_avatar(app: Flask, user_id: str, avatar) -> str:
    with app.app_context():
        if not ALI_API_ID or not ALI_API_SECRET:
            raise_error_with_args(
                "server.api.alibabaCloudNotConfigured",
                config_var="ALIBABA_CLOUD_OSS_ACCESS_KEY_ID,ALIBABA_CLOUD_OSS_ACCESS_KEY_SECRET",
            )
        aggregate = load_user_aggregate(user_id)
        if not aggregate:
            raise_error("USER.USER_NOT_FOUND")

        entity = get_user_entity_by_bid(user_id, include_deleted=True)
        if not entity:
            raise_error("USER.USER_NOT_FOUND")

        file_id = uuid.uuid4().hex
        old_avatar = aggregate.avatar
        if old_avatar:
            old_file_id = old_avatar.split("/")[-1]
            if old_file_id and bucket.object_exists(old_file_id):
                bucket.delete_object(old_file_id)
        bucket.put_object(
            file_id,
            avatar,
            headers={"Content-Type": get_content_type(avatar.filename)},
        )
        url = IMAGE_BASE_URL + "/" + file_id
        update_user_entity_fields(entity, avatar=url)
        db.session.commit()

        from ..shifu.funcs import _warm_up_cdn

        if not _warm_up_cdn(app, url, ALI_API_ID, ALI_API_SECRET, endpoint):
            app.logger.warning(
                "The user avatar URL is inaccessible, but the URL continues to be returned"
            )

        return url
