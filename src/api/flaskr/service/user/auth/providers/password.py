"""密码认证 Provider 实现。

支持通过手机号或邮箱 + 密码登录。
"""

from __future__ import annotations

import json

from flask import Flask

from flaskr.service.user.auth.base import (
    AuthProvider,
    AuthResult,
    VerificationRequest,
)
from flaskr.service.user.auth.factory import (
    has_provider,
    register_provider,
)
from flaskr.service.user.repository import (
    build_user_info_from_aggregate,
    find_credential,
    load_user_aggregate_by_identifier,
)
from flaskr.service.user.password_utils import verify_password
from flaskr.service.user.utils import generate_token
from flaskr.service.common.dtos import UserToken
from flaskr.service.common.models import raise_error


class PasswordAuthProvider(AuthProvider):
    """通过 identifier（手机号或邮箱）+ 密码进行认证。"""

    provider_name = "password"
    supports_challenge = False

    def verify(self, app: Flask, request: VerificationRequest) -> AuthResult:
        identifier = request.identifier.strip()
        password = request.code  # 复用 code 字段传递密码

        if not identifier or not password:
            raise_error("USER.INVALID_CREDENTIALS")

        # 尝试通过 phone 或 email provider 的凭据查找用户
        aggregate = load_user_aggregate_by_identifier(
            identifier, providers=["phone", "email"]
        )
        if not aggregate:
            raise_error("USER.INVALID_CREDENTIALS")

        # 查找 password 类型的凭据
        credential = find_credential(
            provider_name="password",
            identifier=identifier,
            user_bid=aggregate.user_bid,
        )
        if not credential:
            raise_error("USER.INVALID_CREDENTIALS")

        # 从 raw_profile 中取出 password_hash
        try:
            profile_data = (
                json.loads(credential.raw_profile) if credential.raw_profile else {}
            )
        except (json.JSONDecodeError, TypeError):
            profile_data = {}

        password_hash = profile_data.get("password_hash", "")
        if not password_hash or not verify_password(password, password_hash):
            raise_error("USER.INVALID_CREDENTIALS")

        # 构建登录 token
        user_info = build_user_info_from_aggregate(aggregate)
        token = generate_token(app, aggregate.user_bid)
        user_token = UserToken(user_info, token)

        return AuthResult(
            user=user_info,
            token=user_token,
            credential=credential,
            is_new_user=False,
            metadata={"user_bid": aggregate.user_bid},
        )


if not has_provider(PasswordAuthProvider.provider_name):
    register_provider(PasswordAuthProvider)
