"""Post-auth extension orchestration for login and creator-upgrade flows."""

from __future__ import annotations

from dataclasses import dataclass

from flask import Flask

from flaskr.framework.plugin import plugin_manager as plugin_manager_module


@dataclass(slots=True, frozen=True)
class PostAuthContext:
    user_id: str
    source: str
    login_context: str | None = None
    created_new_user: bool = False
    language: str | None = None
    creator_granted_now: bool = False


def run_post_auth_extensions(app: Flask, context: PostAuthContext) -> PostAuthContext:
    """Execute registered post-auth handlers without blocking login success."""

    manager = plugin_manager_module.plugin_manager
    if manager is None:
        return context

    extension_functions = getattr(manager, "extension_functions", {}) or {}
    handlers = list(extension_functions.get("run_post_auth_extensions", []))
    if not handlers:
        return context

    current_context = context
    for handler in handlers:
        handler_name = getattr(handler, "__name__", repr(handler))
        try:
            result = handler(current_context, app=app)
            if isinstance(result, PostAuthContext):
                current_context = result
        except Exception:
            app.logger.exception(
                "Post-auth handler failed: handler=%s user_id=%s source=%s",
                handler_name,
                current_context.user_id,
                current_context.source,
            )
    return current_context
