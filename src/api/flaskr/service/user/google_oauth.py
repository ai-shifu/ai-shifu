# Google OAuth service
# author: claude

from flask import Flask
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google.auth.exceptions import GoogleAuthError

from ...common.config import get_config
from ..common.models import raise_error
from .common import get_model
from ..common.dtos import UserToken
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

    if not GOOGLE_CLIENT_ID:
        raise_error("USER.GOOGLE_OAUTH_NOT_CONFIGURED")

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

        # If we have a temporary user_id from previous session, check for migration
        if not user_info and course_id:
            # Try to find user by email for potential linking
            email_users = User.query.filter(User.email == email).all()

            if len(email_users) > 1:
                # Multiple users with same email - this is a data integrity issue
                app.logger.error(f"Multiple users found with email: {email}")
                raise_error("USER.GOOGLE_EMAIL_AMBIGUOUS")
            elif len(email_users) == 1:
                user_info = email_users[0]
                # Check if the user already has a different Google ID linked
                if user_info.google_id and user_info.google_id != google_id:
                    app.logger.error(
                        f"User with email {email} already linked to different Google account"
                    )
                    raise_error("USER.GOOGLE_ACCOUNT_MISMATCH")
                # Link Google account to existing email user
                user_info.google_id = google_id
                if not user_info.name and name:
                    user_info.name = name

        if not user_info:
            # Check if email already exists before creating new user
            existing_email_user = User.query.filter(User.email == email).first()
            if existing_email_user:
                # Check if the user already has a different Google ID linked
                if (
                    existing_email_user.google_id
                    and existing_email_user.google_id != google_id
                ):
                    app.logger.error(
                        f"User with email {email} already linked to different Google account"
                    )
                    raise_error("USER.GOOGLE_ACCOUNT_MISMATCH")
                # Link Google ID to existing email user
                user_info = existing_email_user
                user_info.google_id = google_id
                if not user_info.name and name:
                    user_info.name = name
            else:
                # No existing user found, will create new one
                pass

        # Use common registration logic
        from .common import (
            _create_or_update_user_registration,
            _build_user_token_response,
        )

        user_info = _create_or_update_user_registration(
            app,
            user_info,
            "google_id",
            google_id,
            language,
            extra_fields={
                "email": email,
                "username": "",  # Keep username empty as per other registration methods
                "name": name,
            },
        )

        try:
            db.session.commit()
        except Exception as e:
            # Handle race condition - another request may have created the user
            db.session.rollback()

            # Try to find the user again
            user_info = User.query.filter(User.google_id == google_id).first()
            if not user_info:
                # If still not found, try by email
                user_info = User.query.filter(User.email == email).first()
                if user_info:
                    # Check if the user already has a different Google ID linked
                    if user_info.google_id and user_info.google_id != google_id:
                        app.logger.error(
                            f"User with email {email} already linked to different Google account"
                        )
                        raise_error("USER.GOOGLE_ACCOUNT_MISMATCH")
                    elif not user_info.google_id:
                        # Link Google ID to existing user
                        user_info.google_id = google_id
                        db.session.commit()

            if not user_info:
                # If still not found, re-raise the original error
                app.logger.error(
                    f"Failed to create user after race condition: {str(e)}"
                )
                raise

        return _build_user_token_response(app, user_info)

    except GoogleAuthError as e:
        app.logger.error(f"Google OAuth verification failed: {str(e)}")
        raise_error("USER.GOOGLE_TOKEN_INVALID")
    except Exception as e:
        app.logger.error(f"Google OAuth error: {str(e)}")
        raise_error("USER.GOOGLE_OAUTH_ERROR")
