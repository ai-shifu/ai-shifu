from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from scripts.observability_consistency_probes import probe_wallet_snapshot


class _Db:
    def __init__(self, session):
        self.session = session


def _build_db():
    engine = create_engine("sqlite:///:memory:")
    session = sessionmaker(bind=engine)()
    session.execute(
        text(
            """
            CREATE TABLE credit_wallets (
              id INTEGER PRIMARY KEY,
              wallet_bid TEXT NOT NULL,
              creator_bid TEXT NOT NULL,
              available_credits NUMERIC NOT NULL,
              reserved_credits NUMERIC NOT NULL,
              deleted INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    )
    session.execute(
        text(
            """
            CREATE TABLE credit_wallet_buckets (
              id INTEGER PRIMARY KEY,
              wallet_bid TEXT NOT NULL,
              creator_bid TEXT NOT NULL,
              available_credits NUMERIC NOT NULL,
              reserved_credits NUMERIC NOT NULL,
              bucket_category INTEGER NOT NULL,
              source_type INTEGER NOT NULL,
              effective_from DATETIME NOT NULL,
              effective_to DATETIME,
              status INTEGER NOT NULL,
              deleted INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    )
    session.execute(
        text(
            """
            CREATE TABLE bill_subscriptions (
              id INTEGER PRIMARY KEY,
              creator_bid TEXT NOT NULL,
              status INTEGER NOT NULL,
              current_period_start_at DATETIME,
              current_period_end_at DATETIME,
              deleted INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    )
    session.commit()
    return SimpleNamespace(engine=engine, session=session, db=_Db(session))


def _args():
    return argparse.Namespace(limit=20)


def _insert_wallet(
    session, *, wallet_bid: str, creator_bid: str, available: str, reserved: str = "0"
):
    session.execute(
        text(
            """
            INSERT INTO credit_wallets (
              wallet_bid, creator_bid, available_credits, reserved_credits, deleted
            ) VALUES (:wallet_bid, :creator_bid, :available, :reserved, 0)
            """
        ),
        {
            "wallet_bid": wallet_bid,
            "creator_bid": creator_bid,
            "available": available,
            "reserved": reserved,
        },
    )


def _insert_bucket(
    session,
    *,
    wallet_bid: str,
    creator_bid: str,
    available: str,
    reserved: str = "0",
    category: int = 7432,
    source_type: int = 7411,
    effective_from: datetime,
    effective_to: datetime | None = None,
):
    session.execute(
        text(
            """
            INSERT INTO credit_wallet_buckets (
              wallet_bid,
              creator_bid,
              available_credits,
              reserved_credits,
              bucket_category,
              source_type,
              effective_from,
              effective_to,
              status,
              deleted
            ) VALUES (
              :wallet_bid,
              :creator_bid,
              :available,
              :reserved,
              :category,
              :source_type,
              :effective_from,
              :effective_to,
              7441,
              0
            )
            """
        ),
        {
            "wallet_bid": wallet_bid,
            "creator_bid": creator_bid,
            "available": available,
            "reserved": reserved,
            "category": category,
            "source_type": source_type,
            "effective_from": effective_from,
            "effective_to": effective_to,
        },
    )


def _insert_active_subscription(session, *, creator_bid: str, now: datetime):
    session.execute(
        text(
            """
            INSERT INTO bill_subscriptions (
              creator_bid,
              status,
              current_period_start_at,
              current_period_end_at,
              deleted
            ) VALUES (:creator_bid, 7202, :start_at, :end_at, 0)
            """
        ),
        {
            "creator_bid": creator_bid,
            "start_at": now - timedelta(days=1),
            "end_at": now + timedelta(days=29),
        },
    )


def _probe(env, *, now: datetime):
    return probe_wallet_snapshot(
        env.db,
        inspect(env.engine),
        _args(),
        now,
        now - timedelta(hours=24),
    )


def test_wallet_snapshot_probe_uses_current_consumable_bucket_total():
    now = datetime(2026, 7, 19, 12, 0, 0)
    env = _build_db()
    _insert_wallet(
        env.session,
        wallet_bid="wallet-topup",
        creator_bid="creator-topup",
        available="100",
    )
    _insert_bucket(
        env.session,
        wallet_bid="wallet-topup",
        creator_bid="creator-topup",
        available="100",
        category=7433,
        source_type=7412,
        effective_from=now - timedelta(days=1),
    )
    env.session.commit()

    result = _probe(env, now=now)

    assert result["status"] == "warning"
    assert result["findings_count"] == 1
    assert result["sample"][0]["wallet_bid"] == "wallet-topup"
    assert result["sample"][0]["current_consumable_bucket_available_credits"] == 0


def test_wallet_snapshot_probe_allows_manual_grants_without_subscription():
    now = datetime(2026, 7, 19, 12, 0, 0)
    env = _build_db()
    _insert_wallet(
        env.session,
        wallet_bid="wallet-manual",
        creator_bid="creator-manual",
        available="25",
    )
    _insert_bucket(
        env.session,
        wallet_bid="wallet-manual",
        creator_bid="creator-manual",
        available="25",
        category=7432,
        source_type=7416,
        effective_from=now - timedelta(days=1),
    )
    env.session.commit()

    result = _probe(env, now=now)

    assert result["status"] == "ok"
    assert result["findings_count"] == 0


def test_wallet_snapshot_probe_counts_reserved_future_buckets_separately():
    now = datetime(2026, 7, 19, 12, 0, 0)
    env = _build_db()
    _insert_wallet(
        env.session,
        wallet_bid="wallet-future",
        creator_bid="creator-future",
        available="0",
        reserved="10",
    )
    _insert_bucket(
        env.session,
        wallet_bid="wallet-future",
        creator_bid="creator-future",
        available="0",
        reserved="10",
        category=7432,
        source_type=7411,
        effective_from=now + timedelta(days=1),
    )
    env.session.commit()

    result = _probe(env, now=now)

    assert result["status"] == "ok"
    assert result["findings_count"] == 0


def test_wallet_snapshot_probe_allows_subscription_and_topup_with_active_subscription():
    now = datetime(2026, 7, 19, 12, 0, 0)
    env = _build_db()
    _insert_wallet(
        env.session,
        wallet_bid="wallet-active",
        creator_bid="creator-active",
        available="120",
    )
    _insert_active_subscription(env.session, creator_bid="creator-active", now=now)
    _insert_bucket(
        env.session,
        wallet_bid="wallet-active",
        creator_bid="creator-active",
        available="80",
        category=7432,
        source_type=7411,
        effective_from=now - timedelta(days=1),
    )
    _insert_bucket(
        env.session,
        wallet_bid="wallet-active",
        creator_bid="creator-active",
        available="40",
        category=7433,
        source_type=7412,
        effective_from=now - timedelta(days=1),
    )
    env.session.commit()

    result = _probe(env, now=now)

    assert result["status"] == "ok"
    assert result["findings_count"] == 0
