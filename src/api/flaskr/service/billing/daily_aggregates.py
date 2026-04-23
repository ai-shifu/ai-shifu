"""Daily aggregate helpers for creator billing reports."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.service.metering.models import BillUsageRecord
from flaskr.util.uuid import generate_id

from .consts import CREDIT_LEDGER_ENTRY_TYPE_CONSUME, CREDIT_SOURCE_TYPE_USAGE
from .models import (
    BillingDailyLedgerSummary,
    BillingDailyUsageMetric,
    CreditLedgerEntry,
)
from .charges import build_usage_metric_charges
from .ownership import resolve_usage_creator_bid
from .primitives import quantize_credit_amount as _quantize_credit_amount
from .primitives import to_decimal as _to_decimal

_ZERO = Decimal("0")


@dataclass(slots=True, frozen=True)
class DailyAggregateJobResult:
    status: str
    stat_date: str
    creator_bid: str | None = None
    shifu_bid: str | None = None
    finalize: bool = False
    window_started_at: str | None = None
    window_ended_at: str | None = None
    usage_count: int = 0
    metric_count: int = 0
    skipped_usage_count: int = 0
    entry_count: int = 0
    row_count: int = 0
    deleted_count: int = 0
    reason: str | None = None

    def to_task_payload(self) -> dict[str, Any]:
        payload = {
            "status": self.status,
            "stat_date": self.stat_date,
            "creator_bid": self.creator_bid,
            "shifu_bid": self.shifu_bid,
            "finalize": self.finalize,
            "window_started_at": self.window_started_at,
            "window_ended_at": self.window_ended_at,
            "usage_count": self.usage_count,
            "metric_count": self.metric_count,
            "skipped_usage_count": self.skipped_usage_count,
            "entry_count": self.entry_count,
            "row_count": self.row_count,
            "deleted_count": self.deleted_count,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload

    def __getitem__(self, key: str) -> Any:
        return self.to_task_payload()[key]


@dataclass(slots=True, frozen=True)
class RebuildDailyAggregatesResult:
    status: str
    creator_bid: str | None
    shifu_bid: str | None
    date_from: str
    date_to: str
    day_count: int
    usage_days: list[DailyAggregateJobResult] = field(default_factory=list)
    ledger_days: list[DailyAggregateJobResult] = field(default_factory=list)

    def to_task_payload(self) -> dict[str, Any]:
        ledger_processed_days = [
            item for item in self.ledger_days if item.status != "skipped"
        ]
        ledger_skipped_days = [
            item for item in self.ledger_days if item.status == "skipped"
        ]
        return {
            "status": self.status,
            "creator_bid": self.creator_bid,
            "shifu_bid": self.shifu_bid,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "day_count": self.day_count,
            "usage": {
                "processed_days": len(self.usage_days),
                "row_count": sum(int(item.row_count or 0) for item in self.usage_days),
                "days": [item.to_task_payload() for item in self.usage_days],
            },
            "ledger": {
                "processed_days": len(ledger_processed_days),
                "skipped_days": len(ledger_skipped_days),
                "row_count": sum(
                    int(item.row_count or 0) for item in ledger_processed_days
                ),
                "days": [item.to_task_payload() for item in self.ledger_days],
            },
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_task_payload()[key]


def aggregate_daily_usage_metrics(
    app: Flask,
    *,
    stat_date: str = "",
    creator_bid: str = "",
    shifu_bid: str = "",
    finalize: bool = False,
    now: datetime | None = None,
) -> DailyAggregateJobResult:
    """Rebuild one day's usage aggregates from usage and ledger details."""

    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_shifu_bid = str(shifu_bid or "").strip()
    window_started_at, window_ended_at, normalized_stat_date = _resolve_stat_window(
        stat_date=stat_date,
        finalize=finalize,
        now=now,
    )

    with app.app_context():
        usage_rows = (
            BillUsageRecord.query.filter(
                BillUsageRecord.deleted == 0,
                BillUsageRecord.record_level == 0,
                BillUsageRecord.billable == 1,
                BillUsageRecord.status == 0,
                BillUsageRecord.created_at >= window_started_at,
                BillUsageRecord.created_at < window_ended_at,
            )
            .order_by(BillUsageRecord.id.asc())
            .all()
        )

        consumed_credit_map = _load_usage_consumed_credit_map(
            window_started_at=window_started_at,
            window_ended_at=window_ended_at,
            creator_bid=normalized_creator_bid,
        )

        aggregates: dict[
            tuple[str, str, int, int, str, str, int],
            dict[str, Any],
        ] = {}
        usage_count = 0
        metric_count = 0
        skipped_usage_count = 0

        for usage in usage_rows:
            resolved_creator_bid = str(
                resolve_usage_creator_bid(app, usage) or ""
            ).strip()
            if not resolved_creator_bid:
                skipped_usage_count += 1
                continue
            if (
                normalized_creator_bid
                and resolved_creator_bid != normalized_creator_bid
            ):
                continue
            if (
                normalized_shifu_bid
                and str(usage.shifu_bid or "").strip() != normalized_shifu_bid
            ):
                continue

            settlement_at = usage.created_at or window_started_at
            metric_charges = build_usage_metric_charges(
                usage,
                settlement_at=settlement_at,
            )
            if not metric_charges:
                skipped_usage_count += 1
                continue

            usage_count += 1
            for charge in metric_charges:
                metric_code = int(charge.billing_metric)
                aggregate_key = (
                    resolved_creator_bid,
                    str(usage.shifu_bid or "").strip(),
                    int(usage.usage_scene or 0),
                    int(usage.usage_type or 0),
                    str(usage.provider or "").strip(),
                    str(usage.model or "").strip(),
                    metric_code,
                )
                row_payload = aggregates.setdefault(
                    aggregate_key,
                    {
                        "creator_bid": resolved_creator_bid,
                        "shifu_bid": str(usage.shifu_bid or "").strip(),
                        "usage_scene": int(usage.usage_scene or 0),
                        "usage_type": int(usage.usage_type or 0),
                        "provider": str(usage.provider or "").strip(),
                        "model": str(usage.model or "").strip(),
                        "billing_metric": metric_code,
                        "raw_amount": 0,
                        "record_count": 0,
                        "consumed_credits": _ZERO,
                    },
                )
                row_payload["raw_amount"] += int(charge.raw_amount)
                row_payload["record_count"] += 1
                row_payload["consumed_credits"] += consumed_credit_map.get(
                    (str(usage.usage_bid or "").strip(), metric_code),
                    _ZERO,
                )
                metric_count += 1

        scope_query = BillingDailyUsageMetric.query.filter(
            BillingDailyUsageMetric.stat_date == normalized_stat_date
        )
        if normalized_creator_bid:
            scope_query = scope_query.filter(
                BillingDailyUsageMetric.creator_bid == normalized_creator_bid
            )
        if normalized_shifu_bid:
            scope_query = scope_query.filter(
                BillingDailyUsageMetric.shifu_bid == normalized_shifu_bid
            )
        deleted_count = int(scope_query.delete(synchronize_session=False) or 0)

        for payload in aggregates.values():
            db.session.add(
                BillingDailyUsageMetric(
                    daily_usage_metric_bid=generate_id(app),
                    stat_date=normalized_stat_date,
                    creator_bid=payload["creator_bid"],
                    shifu_bid=payload["shifu_bid"],
                    usage_scene=payload["usage_scene"],
                    usage_type=payload["usage_type"],
                    provider=payload["provider"],
                    model=payload["model"],
                    billing_metric=payload["billing_metric"],
                    raw_amount=int(payload["raw_amount"]),
                    record_count=int(payload["record_count"]),
                    consumed_credits=_quantize_decimal(payload["consumed_credits"]),
                    window_started_at=window_started_at,
                    window_ended_at=window_ended_at,
                )
            )

        db.session.commit()
        return DailyAggregateJobResult(
            status="finalized" if finalize else "aggregated",
            stat_date=normalized_stat_date,
            creator_bid=normalized_creator_bid or None,
            shifu_bid=normalized_shifu_bid or None,
            finalize=bool(finalize),
            window_started_at=window_started_at.isoformat(),
            window_ended_at=window_ended_at.isoformat(),
            usage_count=usage_count,
            metric_count=metric_count,
            skipped_usage_count=skipped_usage_count,
            row_count=len(aggregates),
            deleted_count=deleted_count,
        )


def finalize_daily_usage_metrics(
    app: Flask,
    *,
    stat_date: str = "",
    creator_bid: str = "",
    shifu_bid: str = "",
    now: datetime | None = None,
) -> DailyAggregateJobResult:
    """Close one day's usage aggregate window by recomputing the full day."""

    return aggregate_daily_usage_metrics(
        app,
        stat_date=stat_date,
        creator_bid=creator_bid,
        shifu_bid=shifu_bid,
        finalize=True,
        now=now,
    )


def aggregate_daily_ledger_summary(
    app: Flask,
    *,
    stat_date: str = "",
    creator_bid: str = "",
    finalize: bool = False,
    now: datetime | None = None,
) -> DailyAggregateJobResult:
    """Rebuild one day's ledger summary directly from ledger detail rows."""

    normalized_creator_bid = str(creator_bid or "").strip()
    window_started_at, window_ended_at, normalized_stat_date = _resolve_stat_window(
        stat_date=stat_date,
        finalize=finalize,
        now=now,
    )

    with app.app_context():
        query = CreditLedgerEntry.query.filter(
            CreditLedgerEntry.deleted == 0,
            CreditLedgerEntry.created_at >= window_started_at,
            CreditLedgerEntry.created_at < window_ended_at,
        )
        if normalized_creator_bid:
            query = query.filter(
                CreditLedgerEntry.creator_bid == normalized_creator_bid
            )
        ledger_rows = query.order_by(CreditLedgerEntry.id.asc()).all()

        aggregates: dict[tuple[str, int, int], dict[str, Any]] = {}
        for row in ledger_rows:
            creator_value = str(row.creator_bid or "").strip()
            if not creator_value:
                continue
            aggregate_key = (
                creator_value,
                int(row.entry_type or 0),
                int(row.source_type or 0),
            )
            row_payload = aggregates.setdefault(
                aggregate_key,
                {
                    "creator_bid": creator_value,
                    "entry_type": int(row.entry_type or 0),
                    "source_type": int(row.source_type or 0),
                    "amount": _ZERO,
                    "entry_count": 0,
                },
            )
            row_payload["amount"] += _to_decimal(row.amount)
            row_payload["entry_count"] += 1

        scope_query = BillingDailyLedgerSummary.query.filter(
            BillingDailyLedgerSummary.stat_date == normalized_stat_date
        )
        if normalized_creator_bid:
            scope_query = scope_query.filter(
                BillingDailyLedgerSummary.creator_bid == normalized_creator_bid
            )
        deleted_count = int(scope_query.delete(synchronize_session=False) or 0)

        for payload in aggregates.values():
            db.session.add(
                BillingDailyLedgerSummary(
                    daily_ledger_summary_bid=generate_id(app),
                    stat_date=normalized_stat_date,
                    creator_bid=payload["creator_bid"],
                    entry_type=payload["entry_type"],
                    source_type=payload["source_type"],
                    amount=_quantize_decimal(payload["amount"]),
                    entry_count=int(payload["entry_count"]),
                    window_started_at=window_started_at,
                    window_ended_at=window_ended_at,
                )
            )

        db.session.commit()
        return DailyAggregateJobResult(
            status="finalized" if finalize else "aggregated",
            stat_date=normalized_stat_date,
            creator_bid=normalized_creator_bid or None,
            finalize=bool(finalize),
            window_started_at=window_started_at.isoformat(),
            window_ended_at=window_ended_at.isoformat(),
            entry_count=len(ledger_rows),
            row_count=len(aggregates),
            deleted_count=deleted_count,
        )


def finalize_daily_ledger_summary(
    app: Flask,
    *,
    stat_date: str = "",
    creator_bid: str = "",
    now: datetime | None = None,
) -> DailyAggregateJobResult:
    """Close one day's ledger summary window by recomputing the full day."""

    return aggregate_daily_ledger_summary(
        app,
        stat_date=stat_date,
        creator_bid=creator_bid,
        finalize=True,
        now=now,
    )


def rebuild_daily_aggregates(
    app: Flask,
    *,
    creator_bid: str = "",
    shifu_bid: str = "",
    date_from: str = "",
    date_to: str = "",
    now: datetime | None = None,
) -> RebuildDailyAggregatesResult:
    """Rebuild usage and ledger daily aggregates across one date window."""

    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_shifu_bid = str(shifu_bid or "").strip()
    start_date, end_date = _resolve_stat_date_range(
        date_from=date_from,
        date_to=date_to,
        now=now,
    )

    usage_days: list[DailyAggregateJobResult] = []
    ledger_days: list[DailyAggregateJobResult] = []
    current_date = start_date
    while current_date <= end_date:
        stat_date = current_date.strftime("%Y-%m-%d")
        usage_days.append(
            aggregate_daily_usage_metrics(
                app,
                stat_date=stat_date,
                creator_bid=normalized_creator_bid,
                shifu_bid=normalized_shifu_bid,
                finalize=True,
            )
        )
        if normalized_shifu_bid:
            ledger_days.append(
                DailyAggregateJobResult(
                    status="skipped",
                    reason="shifu_scope_not_supported",
                    stat_date=stat_date,
                    creator_bid=normalized_creator_bid or None,
                    shifu_bid=normalized_shifu_bid,
                )
            )
        else:
            ledger_days.append(
                aggregate_daily_ledger_summary(
                    app,
                    stat_date=stat_date,
                    creator_bid=normalized_creator_bid,
                    finalize=True,
                )
            )
        current_date += timedelta(days=1)

    return RebuildDailyAggregatesResult(
        status="rebuilt",
        creator_bid=normalized_creator_bid or None,
        shifu_bid=normalized_shifu_bid or None,
        date_from=start_date.strftime("%Y-%m-%d"),
        date_to=end_date.strftime("%Y-%m-%d"),
        day_count=len(usage_days),
        usage_days=usage_days,
        ledger_days=ledger_days,
    )


def detect_daily_aggregate_rebuild_range(
    app: Flask,
    *,
    creator_bid: str = "",
    shifu_bid: str = "",
) -> tuple[str | None, str | None]:
    """Detect the earliest and latest stat_date that currently need rebuild."""

    normalized_creator_bid = str(creator_bid or "").strip()
    normalized_shifu_bid = str(shifu_bid or "").strip()

    with app.app_context():
        candidate_dates: list[datetime] = []

        usage_rows = (
            BillUsageRecord.query.filter(
                BillUsageRecord.deleted == 0,
                BillUsageRecord.record_level == 0,
                BillUsageRecord.billable == 1,
                BillUsageRecord.status == 0,
            )
            .order_by(BillUsageRecord.created_at.asc(), BillUsageRecord.id.asc())
            .all()
        )
        for usage in usage_rows:
            if (
                normalized_shifu_bid
                and str(usage.shifu_bid or "").strip() != normalized_shifu_bid
            ):
                continue
            if normalized_creator_bid:
                resolved_creator_bid = str(
                    resolve_usage_creator_bid(app, usage) or ""
                ).strip()
                if resolved_creator_bid != normalized_creator_bid:
                    continue
            if usage.created_at is not None:
                candidate_dates.append(usage.created_at)

        ledger_query = CreditLedgerEntry.query.filter(CreditLedgerEntry.deleted == 0)
        if normalized_creator_bid:
            ledger_query = ledger_query.filter(
                CreditLedgerEntry.creator_bid == normalized_creator_bid
            )
        if not normalized_shifu_bid:
            for row in ledger_query.order_by(
                CreditLedgerEntry.created_at.asc(),
                CreditLedgerEntry.id.asc(),
            ).all():
                if row.created_at is not None:
                    candidate_dates.append(row.created_at)

    if not candidate_dates:
        return None, None

    candidate_dates.sort()
    return (
        candidate_dates[0].strftime("%Y-%m-%d"),
        candidate_dates[-1].strftime("%Y-%m-%d"),
    )


def _load_usage_consumed_credit_map(
    *,
    window_started_at: datetime,
    window_ended_at: datetime,
    creator_bid: str = "",
) -> dict[tuple[str, int], Decimal]:
    query = CreditLedgerEntry.query.filter(
        CreditLedgerEntry.deleted == 0,
        CreditLedgerEntry.entry_type == CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
        CreditLedgerEntry.source_type == CREDIT_SOURCE_TYPE_USAGE,
        CreditLedgerEntry.created_at >= window_started_at,
        CreditLedgerEntry.created_at < window_ended_at,
    )
    normalized_creator_bid = str(creator_bid or "").strip()
    if normalized_creator_bid:
        query = query.filter(CreditLedgerEntry.creator_bid == normalized_creator_bid)
    rows = query.order_by(CreditLedgerEntry.id.asc()).all()

    consumed_map: defaultdict[tuple[str, int], Decimal] = defaultdict(lambda: _ZERO)
    for row in rows:
        usage_bid = str(row.source_bid or "").strip()
        if not usage_bid:
            continue
        metric_breakdown = list((row.metadata_json or {}).get("metric_breakdown") or [])
        if not metric_breakdown:
            continue
        for item in metric_breakdown:
            try:
                metric_code = int(item.get("billing_metric_code") or 0)
            except (TypeError, ValueError):
                continue
            if metric_code <= 0:
                continue
            consumed_credits = item.get("consumed_credits")
            if consumed_credits in (None, ""):
                consumed_value = _quantize_decimal(-_to_decimal(row.amount))
            else:
                consumed_value = _quantize_decimal(consumed_credits)
            consumed_map[(usage_bid, metric_code)] += consumed_value
    return dict(consumed_map)


def _resolve_stat_window(
    *,
    stat_date: str = "",
    finalize: bool = False,
    now: datetime | None = None,
) -> tuple[datetime, datetime, str]:
    anchor = now or datetime.now()
    normalized_stat_date = str(stat_date or "").strip() or anchor.strftime("%Y-%m-%d")
    day_start = datetime.strptime(normalized_stat_date, "%Y-%m-%d")
    day_end = day_start + timedelta(days=1)
    if finalize:
        return day_start, day_end, normalized_stat_date
    return day_start, min(anchor, day_end), normalized_stat_date


def _resolve_stat_date_range(
    *,
    date_from: str = "",
    date_to: str = "",
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    anchor = now or datetime.now()
    normalized_date_from = str(date_from or "").strip()
    normalized_date_to = str(date_to or "").strip()
    start_value = (
        normalized_date_from or normalized_date_to or anchor.strftime("%Y-%m-%d")
    )
    end_value = (
        normalized_date_to or normalized_date_from or anchor.strftime("%Y-%m-%d")
    )
    start_date = datetime.strptime(start_value, "%Y-%m-%d")
    end_date = datetime.strptime(end_value, "%Y-%m-%d")
    if end_date < start_date:
        raise ValueError("date_to must be greater than or equal to date_from")
    return start_date, end_date


def _quantize_decimal(value: Any) -> Decimal:
    return _quantize_credit_amount(value)
