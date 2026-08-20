"""Shared service models, errors and dictionaries."""

from flaskr.util.deprecation import deprecated_alias_getattr

from .models import *  # noqa: F403

__getattr__ = deprecated_alias_getattr(
    __name__, {"AppException": "AppError"}, globals()
)
