# user service
# author: yfge
#


import uuid
from flask import Flask

from ..common.models import raise_error

from .utils import generate_token
from ...service.common.dtos import USER_STATE_UNREGISTERED, UserToken
from ...service.user.models import UserConversion
from ...dao import db
from ...api.wechat import get_wechat_access_token
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
from flaskr.service.common.oss_utils import (
    OSS_PROFILE_DEFAULT,
    create_oss_bucket,
    get_image_content_type,
    get_oss_config,
    upload_to_oss,
    warm_up_cdn,
)

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


def upload_user_avatar(app: Flask, user_id: str, avatar) -> str:
    with app.app_context():
        config = get_oss_config(OSS_PROFILE_DEFAULT)
        bucket = create_oss_bucket(config)
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

        url, _bucket_name = upload_to_oss(
            app,
            file_content=avatar,
            file_id=file_id,
            content_type=get_image_content_type(avatar.filename),
            profile=OSS_PROFILE_DEFAULT,
            config=config,
            bucket=bucket,
            warm_up=False,
        )
        update_user_entity_fields(entity, avatar=url)
        db.session.commit()

        if not warm_up_cdn(app, url, config):
            app.logger.warning(
                "The user avatar URL is inaccessible, but the URL continues to be returned"
            )

        return url
