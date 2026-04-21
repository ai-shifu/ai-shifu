"""Billing post-auth extension hooks."""

from __future__ import annotations

from flask import Flask

from flaskr.framework.plugin.plugin_manager import extension
from flaskr.service.user.post_auth import PostAuthContext

from .trials import bootstrap_new_creator_trial_credits


@extension("run_post_auth_extensions")
def bootstrap_creator_trial_post_auth(
    context: PostAuthContext,
    *,
    app: Flask,
) -> PostAuthContext:
    """Best-effort trial bootstrap for successful auth flows."""

    if not context.creator_granted_now:
        return context

    try:
        bootstrap_new_creator_trial_credits(app, context.user_id)
    except Exception:
        app.logger.exception(
            "Billing post-auth trial bootstrap failed for user_id=%s source=%s",
            context.user_id,
            context.source,
        )
    return context
