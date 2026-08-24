"""Referral post-auth hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flaskr.framework.plugin.plugin_manager import extension

from .service import process_referral_post_auth

if TYPE_CHECKING:
    from flask import Flask


@extension("run_post_auth_extensions")
def bind_referral_invite_post_auth(
    context: object,
    *,
    app: Flask,
) -> object:
    """Best-effort referral binding for new SMS-created users."""
    try:
        process_referral_post_auth(app, context)
    except Exception:
        app.logger.exception(
            "Referral post-auth binding failed: user_id=%s source=%s invite_code=%s",
            context.user_id,
            context.source,
            context.invite_code,
        )
    return context
