# Google OAuth service
# author: claude

import uuid
from flask import Flask
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google.auth.exceptions import GoogleAuthError

from ...common.config import get_config
from ..common.models import raise_error
from .common import get_model
from ..common.dtos import (
    USER_STATE_REGISTERED,
    USER_STATE_UNREGISTERED,
    UserInfo,
    UserToken,
)
from .utils import generate_token
from ...dao import db


GOOGLE_CLIENT_ID = get_config("GOOGLE_OAUTH_CLIENT_ID", None)


def verify_google_token(
    app: Flask, id_token_str: str, course_id: str = None, language: str = None
) -> UserToken:
    """
    Verify Google OAuth ID token and create/login user

    Args:
        app: Flask application instance
        id_token_str: Google ID token string
        course_id: Optional course ID for user registration context
        language: User's preferred language

    Returns:
        UserToken: Contains user info and access token

    Raises:
        Various user errors via raise_error
    """
    User = get_model(app)

    # TODO: Implement course_id logic similar to verify_sms_code/verify_mail_code
    # This would handle profile migration and study record migration when users
    # link their Google accounts. Currently kept for API consistency.

    if not GOOGLE_CLIENT_ID:
        raise_error("USER.GOOGLE_OAUTH_NOT_CONFIGURED")

    with app.app_context():
        try:
            # Verify the ID token
            id_info = id_token.verify_oauth2_token(
                id_token_str, google_requests.Request(), GOOGLE_CLIENT_ID
            )

            # Extract user information from the token
            google_id = id_info.get("sub")
            email = id_info.get("email")
            name = id_info.get("name", "")
            email_verified = id_info.get("email_verified", False)

            if not google_id or not email:
                raise_error("USER.GOOGLE_TOKEN_INVALID")

            if not email_verified:
                raise_error("USER.GOOGLE_EMAIL_NOT_VERIFIED")

            # Try to find existing user by Google ID first
            user_info = User.query.filter(User.google_id == google_id).first()

            if not user_info:
                # Try to find user by email
                user_info = User.query.filter(User.email == email).first()

                if user_info:
                    # Link Google account to existing email user
                    user_info.google_id = google_id
                    if not user_info.name:
                        user_info.name = name
                else:
                    # Create new user
                    user_id = str(uuid.uuid4()).replace("-", "")
                    user_info = User(
                        user_id=user_id,
                        username=email,  # Use email as username
                        name=name,
                        email=email,
                        mobile="",
                        google_id=google_id,
                        user_state=USER_STATE_REGISTERED,
                        user_language=language or "en-US",
                    )
                    db.session.add(user_info)

                    # Initialize first course if needed
                    from .common import init_first_course

                    init_first_course(app, user_id)

            # Ensure user is registered state
            if user_info.user_state == USER_STATE_UNREGISTERED:
                user_info.user_state = USER_STATE_REGISTERED
                if language:
                    user_info.user_language = language

            # Generate access token
            token = generate_token(app, user_id=user_info.user_id)

            db.session.commit()

            return UserToken(
                UserInfo(
                    user_id=user_info.user_id,
                    username=user_info.username,
                    name=user_info.name,
                    email=user_info.email,
                    mobile=user_info.mobile,
                    user_state=user_info.user_state,
                    wx_openid=getattr(user_info, "user_open_id", ""),
                    language=getattr(user_info, "user_language", "en-US"),
                    user_avatar=getattr(user_info, "user_avatar", ""),
                    has_password=bool(getattr(user_info, "password_hash", "")),
                    is_admin=getattr(user_info, "is_admin", False),
                    is_creator=getattr(user_info, "is_creator", False),
                ),
                token=token,
            )

        except GoogleAuthError as e:
            app.logger.error(f"Google OAuth verification failed: {str(e)}")
            raise_error("USER.GOOGLE_TOKEN_INVALID")
        except Exception as e:
            app.logger.error(f"Google OAuth error: {str(e)}")
            raise_error("USER.GOOGLE_OAUTH_ERROR")


def unlink_google_account(app: Flask, user_id: str) -> bool:
    """
    Unlink Google account from user

    Args:
        app: Flask application instance
        user_id: User ID to unlink Google account from

    Returns:
        bool: True if successful
    """
    User = get_model(app)

    with app.app_context():
        user = User.query.filter_by(user_id=user_id).first()
        if not user:
            raise_error("USER.USER_NOT_FOUND")

        if not user.google_id:
            raise_error("USER.GOOGLE_ACCOUNT_NOT_LINKED")

        # Ensure user has password or other login method before unlinking
        if not user.password_hash and not user.mobile and not user.user_open_id:
            raise_error("USER.CANNOT_UNLINK_ONLY_LOGIN_METHOD")

        user.google_id = None
        db.session.commit()

        return True
