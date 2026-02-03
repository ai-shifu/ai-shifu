import datetime

from flask import Flask, request
from sqlalchemy import func

from flaskr.framework.plugin.inject import inject
from flaskr.route.common import make_common_response
from flaskr.service.common.models import raise_param_error
from flaskr.service.metering.models import BillingUsageRecord


def _parse_date(value: str, *, field_name: str) -> datetime.datetime:
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise_param_error(f"Invalid {field_name} format, expected YYYY-MM-DD")


@inject
def register_metering_routes(app: Flask, path_prefix: str = "/api/metering") -> Flask:
    """Register metering routes."""

    @app.route(path_prefix + "/usage-summary", methods=["GET"])
    def get_usage_summary():
        start_date = request.args.get("start_date", "")
        end_date = request.args.get("end_date", "")
        user_bid = request.args.get("user_bid", "")
        shifu_bid = request.args.get("shifu_bid", "")
        usage_scene = request.args.get("usage_scene", "")

        query = BillingUsageRecord.query.filter(
            BillingUsageRecord.deleted == 0,
            BillingUsageRecord.record_level == 0,
        )

        if start_date:
            start_dt = _parse_date(start_date, field_name="start_date")
            query = query.filter(BillingUsageRecord.created_at >= start_dt)
        if end_date:
            end_dt = _parse_date(end_date, field_name="end_date")
            end_dt = end_dt + datetime.timedelta(days=1)
            query = query.filter(BillingUsageRecord.created_at < end_dt)
        if user_bid:
            query = query.filter(BillingUsageRecord.user_bid == user_bid)
        if shifu_bid:
            query = query.filter(BillingUsageRecord.shifu_bid == shifu_bid)
        if usage_scene != "":
            try:
                scene_value = int(usage_scene)
            except ValueError:
                raise_param_error("usage_scene must be an integer")
            query = query.filter(BillingUsageRecord.usage_scene == scene_value)

        llm_summary = (
            query.filter(BillingUsageRecord.usage_type == 1)
            .with_entities(
                func.coalesce(func.sum(BillingUsageRecord.input), 0),
                func.coalesce(func.sum(BillingUsageRecord.output), 0),
                func.coalesce(func.sum(BillingUsageRecord.total), 0),
                func.coalesce(func.count(BillingUsageRecord.id), 0),
            )
            .first()
        )
        tts_summary = (
            query.filter(BillingUsageRecord.usage_type == 2)
            .with_entities(
                func.coalesce(func.sum(BillingUsageRecord.input), 0),
                func.coalesce(func.sum(BillingUsageRecord.output), 0),
                func.coalesce(func.sum(BillingUsageRecord.total), 0),
                func.coalesce(func.sum(BillingUsageRecord.word_count), 0),
                func.coalesce(func.sum(BillingUsageRecord.duration_ms), 0),
                func.coalesce(func.count(BillingUsageRecord.id), 0),
            )
            .first()
        )

        data = {
            "llm": {
                "input": int(llm_summary[0] or 0),
                "output": int(llm_summary[1] or 0),
                "total": int(llm_summary[2] or 0),
                "count": int(llm_summary[3] or 0),
            },
            "tts": {
                "input": int(tts_summary[0] or 0),
                "output": int(tts_summary[1] or 0),
                "total": int(tts_summary[2] or 0),
                "word_count": int(tts_summary[3] or 0),
                "duration_ms": int(tts_summary[4] or 0),
                "count": int(tts_summary[5] or 0),
            },
        }

        return make_common_response(data=data)

    return app
