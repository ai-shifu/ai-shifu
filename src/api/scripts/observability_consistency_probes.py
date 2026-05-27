#!/usr/bin/env python3
"""Run read-only observability consistency probes against the application DB."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable

from sqlalchemy import inspect, text


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")

CREDIT_BUCKET_STATUS_ACTIVE = 7441
CREDIT_LEDGER_ENTRY_TYPE_CONSUME = 7402
CREDIT_SOURCE_TYPE_USAGE = 7414

ProbeFn = Callable[[Any, Any, argparse.Namespace, datetime, datetime], dict[str, Any]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run read-only billing, wallet, model, SMS, and notification "
            "consistency probes. Output is JSON."
        )
    )
    parser.add_argument(
        "--probe",
        action="append",
        default=[],
        choices=[
            "all",
            "usage-ledger",
            "wallet-snapshot",
            "bucket-expiration",
            "model-override-inventory",
            "sms-send-failures",
            "notification-template-sync",
        ],
        help="Probe to run. Repeatable. Defaults to all.",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=24,
        help="Lookback window for time-bounded probes.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum sample rows per probe.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to write the JSON report.",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return nonzero when warning/error probes find rows.",
    )
    return parser


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def row_to_dict(row: Any) -> dict[str, Any]:
    return {key: json_safe(value) for key, value in dict(row).items()}


def table_has_columns(inspector: Any, table_name: str, columns: set[str]) -> bool:
    if table_name not in set(inspector.get_table_names()):
        return False
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    return columns.issubset(existing)


def skipped_probe(name: str, description: str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "status": "skipped",
        "severity": "none",
        "findings_count": 0,
        "sample": [],
        "reason": reason,
    }


def rows_probe(
    *,
    name: str,
    description: str,
    rows: list[dict[str, Any]],
    severity: str = "warning",
    status_when_found: str = "warning",
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "status": status_when_found if rows else "ok",
        "severity": severity if rows else "none",
        "findings_count": len(rows),
        "sample": rows,
    }


def execute_rows(db: Any, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    rows = db.session.execute(text(sql), params).mappings().all()
    return [row_to_dict(row) for row in rows]


def probe_usage_ledger(
    db: Any,
    inspector: Any,
    args: argparse.Namespace,
    now: datetime,
    since: datetime,
) -> dict[str, Any]:
    description = (
        "Successful billable top-level usage rows missing consume ledger entries."
    )
    if not table_has_columns(
        inspector,
        "bill_usage",
        {"usage_bid", "billable", "status", "record_level", "deleted", "created_at"},
    ) or not table_has_columns(
        inspector,
        "credit_ledger_entries",
        {"source_type", "source_bid", "entry_type", "deleted"},
    ):
        return skipped_probe("usage-ledger", description, "required tables are missing")

    rows = execute_rows(
        db,
        """
        SELECT
          u.id,
          u.usage_bid,
          u.user_bid,
          u.shifu_bid,
          u.usage_type,
          u.usage_scene,
          u.provider,
          u.model,
          u.request_id,
          u.trace_id,
          u.created_at
        FROM bill_usage u
        LEFT JOIN credit_ledger_entries le
          ON le.source_type = :usage_source_type
         AND le.source_bid = u.usage_bid
         AND le.entry_type = :consume_entry_type
         AND le.deleted = 0
        WHERE u.deleted = 0
          AND u.billable = 1
          AND u.status = 0
          AND u.record_level = 0
          AND u.created_at >= :since
          AND le.id IS NULL
        ORDER BY u.created_at DESC
        LIMIT :limit
        """,
        {
            "usage_source_type": CREDIT_SOURCE_TYPE_USAGE,
            "consume_entry_type": CREDIT_LEDGER_ENTRY_TYPE_CONSUME,
            "since": since,
            "limit": args.limit,
        },
    )
    return rows_probe(name="usage-ledger", description=description, rows=rows)


def probe_wallet_snapshot(
    db: Any,
    inspector: Any,
    args: argparse.Namespace,
    now: datetime,
    since: datetime,
) -> dict[str, Any]:
    description = (
        "Wallet available/reserved totals that differ from active bucket totals."
    )
    if not table_has_columns(
        inspector,
        "credit_wallets",
        {
            "wallet_bid",
            "creator_bid",
            "available_credits",
            "reserved_credits",
            "deleted",
        },
    ) or not table_has_columns(
        inspector,
        "credit_wallet_buckets",
        {
            "wallet_bid",
            "available_credits",
            "reserved_credits",
            "effective_from",
            "effective_to",
            "status",
            "deleted",
        },
    ):
        return skipped_probe(
            "wallet-snapshot", description, "required tables are missing"
        )

    rows = execute_rows(
        db,
        """
        SELECT *
        FROM (
          SELECT
            w.wallet_bid,
            w.creator_bid,
            w.available_credits AS wallet_available_credits,
            w.reserved_credits AS wallet_reserved_credits,
            COALESCE(SUM(CASE
              WHEN b.deleted = 0
               AND b.status = :active_status
               AND b.effective_from <= :now
               AND (b.effective_to IS NULL OR b.effective_to > :now)
              THEN b.available_credits
              ELSE 0
            END), 0) AS active_bucket_available_credits,
            COALESCE(SUM(CASE
              WHEN b.deleted = 0
               AND b.status = :active_status
               AND b.effective_from <= :now
               AND (b.effective_to IS NULL OR b.effective_to > :now)
              THEN b.reserved_credits
              ELSE 0
            END), 0) AS active_bucket_reserved_credits
          FROM credit_wallets w
          LEFT JOIN credit_wallet_buckets b
            ON b.wallet_bid = w.wallet_bid
          WHERE w.deleted = 0
          GROUP BY
            w.wallet_bid,
            w.creator_bid,
            w.available_credits,
            w.reserved_credits
        ) snapshot
        WHERE ABS(wallet_available_credits - active_bucket_available_credits) > :epsilon
           OR ABS(wallet_reserved_credits - active_bucket_reserved_credits) > :epsilon
        ORDER BY wallet_bid
        LIMIT :limit
        """,
        {
            "active_status": CREDIT_BUCKET_STATUS_ACTIVE,
            "now": now,
            "epsilon": Decimal("0.000001"),
            "limit": args.limit,
        },
    )
    return rows_probe(name="wallet-snapshot", description=description, rows=rows)


def probe_bucket_expiration(
    db: Any,
    inspector: Any,
    args: argparse.Namespace,
    now: datetime,
    since: datetime,
) -> dict[str, Any]:
    description = (
        "Credit buckets whose status does not match expiration/available state."
    )
    if not table_has_columns(
        inspector,
        "credit_wallet_buckets",
        {
            "wallet_bucket_bid",
            "wallet_bid",
            "creator_bid",
            "available_credits",
            "effective_to",
            "status",
            "deleted",
            "updated_at",
        },
    ):
        return skipped_probe(
            "bucket-expiration", description, "required table is missing"
        )

    rows = execute_rows(
        db,
        """
        SELECT
          wallet_bucket_bid,
          wallet_bid,
          creator_bid,
          available_credits,
          reserved_credits,
          effective_from,
          effective_to,
          status,
          updated_at
        FROM credit_wallet_buckets
        WHERE deleted = 0
          AND (
            (status = :active_status AND effective_to IS NOT NULL AND effective_to <= :now)
            OR
            (status <> :active_status AND available_credits > :epsilon
              AND (effective_to IS NULL OR effective_to > :now))
          )
        ORDER BY updated_at DESC
        LIMIT :limit
        """,
        {
            "active_status": CREDIT_BUCKET_STATUS_ACTIVE,
            "now": now,
            "epsilon": Decimal("0.000001"),
            "limit": args.limit,
        },
    )
    return rows_probe(name="bucket-expiration", description=description, rows=rows)


def probe_model_override_inventory(
    db: Any,
    inspector: Any,
    args: argparse.Namespace,
    now: datetime,
    since: datetime,
) -> dict[str, Any]:
    description = (
        "Published outline items whose explicit model differs from course defaults."
    )
    if not table_has_columns(
        inspector,
        "shifu_published_shifus",
        {"id", "shifu_bid", "title", "llm", "ask_llm", "deleted"},
    ) or not table_has_columns(
        inspector,
        "shifu_published_outline_items",
        {"id", "outline_item_bid", "shifu_bid", "title", "llm", "ask_llm", "deleted"},
    ):
        return skipped_probe(
            "model-override-inventory",
            description,
            "required tables are missing",
        )

    rows = execute_rows(
        db,
        """
        SELECT
          o.shifu_bid,
          s.title AS shifu_title,
          o.outline_item_bid,
          o.title AS outline_title,
          s.llm AS course_llm,
          o.llm AS outline_llm,
          s.ask_llm AS course_ask_llm,
          o.ask_llm AS outline_ask_llm
        FROM shifu_published_outline_items o
        JOIN (
          SELECT outline_item_bid, MAX(id) AS max_id
          FROM shifu_published_outline_items
          WHERE deleted = 0
          GROUP BY outline_item_bid
        ) latest_o ON latest_o.max_id = o.id
        JOIN shifu_published_shifus s
          ON s.shifu_bid = o.shifu_bid
        JOIN (
          SELECT shifu_bid, MAX(id) AS max_id
          FROM shifu_published_shifus
          WHERE deleted = 0
          GROUP BY shifu_bid
        ) latest_s ON latest_s.max_id = s.id
        WHERE o.deleted = 0
          AND s.deleted = 0
          AND (
            (TRIM(COALESCE(o.llm, '')) <> ''
              AND TRIM(COALESCE(s.llm, '')) <> ''
              AND TRIM(o.llm) <> TRIM(s.llm))
            OR
            (TRIM(COALESCE(o.ask_llm, '')) <> ''
              AND TRIM(COALESCE(s.ask_llm, '')) <> ''
              AND TRIM(o.ask_llm) <> TRIM(s.ask_llm))
          )
        ORDER BY o.updated_at DESC
        LIMIT :limit
        """,
        {"limit": args.limit},
    )
    return rows_probe(
        name="model-override-inventory",
        description=description,
        rows=rows,
        severity="info",
        status_when_found="info",
    )


def probe_sms_send_failures(
    db: Any,
    inspector: Any,
    args: argparse.Namespace,
    now: datetime,
    since: datetime,
) -> dict[str, Any]:
    description = "Recent SMS verification-code rows that were created but not sent."
    if not table_has_columns(
        inspector,
        "user_verify_code",
        {"id", "phone", "verify_code_type", "verify_code_send", "created"},
    ):
        return skipped_probe(
            "sms-send-failures", description, "required table is missing"
        )

    rows = execute_rows(
        db,
        """
        SELECT
          id,
          phone,
          user_ip,
          verify_code_type,
          verify_code_send,
          verify_code_used,
          created
        FROM user_verify_code
        WHERE verify_code_type = 1
          AND verify_code_send = 0
          AND created >= :since
        ORDER BY created DESC
        LIMIT :limit
        """,
        {"since": since, "limit": args.limit},
    )
    return rows_probe(name="sms-send-failures", description=description, rows=rows)


def probe_notification_template_sync(
    db: Any,
    inspector: Any,
    args: argparse.Namespace,
    now: datetime,
    since: datetime,
) -> dict[str, Any]:
    description = "Notification templates whose latest provider sync is not successful."
    if not table_has_columns(
        inspector,
        "notification_templates",
        {
            "notification_template_bid",
            "channel",
            "provider",
            "template_code",
            "sync_status",
            "error_code",
            "last_synced_at",
            "deleted",
        },
    ):
        return skipped_probe(
            "notification-template-sync",
            description,
            "required table is missing",
        )

    rows = execute_rows(
        db,
        """
        SELECT
          notification_template_bid,
          channel,
          provider,
          template_code,
          template_name,
          sync_status,
          error_code,
          error_message,
          last_synced_at,
          updated_at
        FROM notification_templates
        WHERE deleted = 0
          AND sync_status <> 'synced'
        ORDER BY updated_at DESC
        LIMIT :limit
        """,
        {"limit": args.limit},
    )
    return rows_probe(
        name="notification-template-sync",
        description=description,
        rows=rows,
    )


PROBES: dict[str, ProbeFn] = {
    "usage-ledger": probe_usage_ledger,
    "wallet-snapshot": probe_wallet_snapshot,
    "bucket-expiration": probe_bucket_expiration,
    "model-override-inventory": probe_model_override_inventory,
    "sms-send-failures": probe_sms_send_failures,
    "notification-template-sync": probe_notification_template_sync,
}


def selected_probe_names(raw_names: list[str]) -> list[str]:
    if not raw_names or "all" in raw_names:
        return list(PROBES)
    deduped: list[str] = []
    for name in raw_names:
        if name not in deduped:
            deduped.append(name)
    return deduped


def summarize(probes: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [str(probe.get("status") or "") for probe in probes]
    finding_count = sum(int(probe.get("findings_count") or 0) for probe in probes)
    blocking_count = sum(
        int(probe.get("findings_count") or 0)
        for probe in probes
        if probe.get("status") in {"warning", "error"}
    )
    return {
        "probe_count": len(probes),
        "finding_count": finding_count,
        "blocking_finding_count": blocking_count,
        "ok_count": statuses.count("ok"),
        "info_count": statuses.count("info"),
        "warning_count": statuses.count("warning"),
        "error_count": statuses.count("error"),
        "skipped_count": statuses.count("skipped"),
    }


def run_report(args: argparse.Namespace) -> dict[str, Any]:
    from dotenv import load_dotenv  # noqa: WPS433
    from flask import Flask  # noqa: WPS433
    from flaskr.common.config import Config  # noqa: WPS433
    from flaskr import dao  # noqa: WPS433
    import pymysql  # noqa: WPS433

    if not os.getenv("SKIP_LOAD_DOTENV"):
        load_dotenv()

    app = Flask("observability-consistency-probes")
    app.config = Config(app.config, app)
    timezone = str(app.config.get("TZ") or "").strip()
    if timezone:
        os.environ["TZ"] = timezone
        time.tzset()
    pymysql.install_as_MySQLdb()
    dao.init_db(app)
    db = dao.db
    now = datetime.now()
    since = now - timedelta(hours=args.window_hours)
    with app.app_context():
        inspector = inspect(db.session.get_bind())
        probes = [
            PROBES[name](db, inspector, args, now, since)
            for name in selected_probe_names(args.probe)
        ]

    return {
        "schema_version": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "window_hours": args.window_hours,
        "limit": args.limit,
        "summary": summarize(probes),
        "probes": probes,
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.window_hours <= 0:
        parser.error("--window-hours must be greater than 0")
    if args.limit <= 0:
        parser.error("--limit must be greater than 0")

    report = run_report(args)
    output = json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    print(output, end="")

    if args.fail_on_findings and report["summary"]["blocking_finding_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
