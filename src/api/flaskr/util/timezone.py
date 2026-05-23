from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask


def get_app_timezone(app: Flask, tz_name: str | None = None) -> ZoneInfo:
    fallback_tz_name = app.config.get("TZ", "UTC")
    candidate_tz_name = (tz_name or fallback_tz_name or "UTC").strip()
    try:
        return ZoneInfo(candidate_tz_name)
    except ZoneInfoNotFoundError as error:
        app.logger.warning(
            "Failed to load timezone '%s': %s, falling back to '%s'",
            candidate_tz_name,
            error,
            fallback_tz_name,
        )
    except Exception as error:
        app.logger.warning(
            "Unexpected timezone config '%s': %s, falling back to UTC",
            candidate_tz_name,
            error,
        )

    if candidate_tz_name != fallback_tz_name:
        try:
            return ZoneInfo(fallback_tz_name)
        except ZoneInfoNotFoundError as error:
            app.logger.warning(
                "Failed to load fallback timezone '%s': %s, falling back to UTC",
                fallback_tz_name,
                error,
            )
        except Exception as error:
            app.logger.warning(
                "Unexpected fallback timezone config '%s': %s, falling back to UTC",
                fallback_tz_name,
                error,
            )

    return ZoneInfo("UTC")


def _coerce_datetime(app: Flask, value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        stripped_value = value.strip()
        if not stripped_value:
            return None
        normalized_value = (
            f"{stripped_value[:-1]}+00:00"
            if stripped_value.endswith("Z")
            else stripped_value
        )
        try:
            return datetime.fromisoformat(normalized_value)
        except ValueError:
            app.logger.warning(
                "Failed to parse datetime string '%s' for timezone conversion",
                stripped_value,
            )
            return None
    app.logger.warning(
        "Unexpected datetime value type '%s' for timezone conversion",
        type(value).__name__,
    )
    return None


def serialize_with_app_timezone(
    app: Flask,
    dt: datetime | str | None,
    tz_name: str | None = None,
) -> str | None:
    dt = _coerce_datetime(app, dt)
    if dt is None:
        return None
    app_tz = get_app_timezone(app, tz_name)
    if dt.tzinfo is None:
        source_tz = get_app_timezone(app)
        dt = dt.replace(tzinfo=source_tz)
    return dt.astimezone(app_tz).isoformat()


def format_with_app_timezone(
    app: Flask,
    dt: datetime | str | None,
    fmt: str,
    tz_name: str | None = None,
) -> str | None:
    dt = _coerce_datetime(app, dt)
    if dt is None:
        return None
    app_tz = get_app_timezone(app, tz_name)
    if dt.tzinfo is None:
        source_tz = get_app_timezone(app)
        dt = dt.replace(tzinfo=source_tz)
    return dt.astimezone(app_tz).strftime(fmt)
