"""Subprocess probe for real MySQL course-identifier allocation races."""

# ruff: noqa: E402

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
from threading import Barrier, Lock


API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

os.environ["SKIP_LOAD_DOTENV"] = "1"
os.environ["SKIP_APP_AUTOCREATE"] = "1"
os.environ["SECRET_KEY"] = "mysql-slug-concurrency"
os.environ["DEFAULT_LLM_MODEL"] = "gpt-test"
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["REDIS_HOST"] = ""
os.environ["REDIS_PORT"] = ""
os.environ["SAAS_DB_URI"] = os.environ["SQLALCHEMY_DATABASE_URI"]
os.environ["ADMIN_DB_URI"] = os.environ["SQLALCHEMY_DATABASE_URI"]

from app import create_app


app = create_app()

from flaskr.dao import db
from flaskr.service.shifu import slug as slug_module
from flaskr.service.shifu.models import (
    DraftShifu,
    ShifuCourseSlug,
    ShifuPublicIdentifier,
)
from flaskr.service.shifu.slug import (
    PreparedCourseSlug,
    ShifuIdentifierConflict,
    allocate_course_slug,
    resolve_shifu_identifier,
)


def _allocate_course(barrier: Barrier, *, shifu_bid: str, base_slug: str) -> dict:
    with app.app_context():
        barrier.wait(timeout=20)
        try:
            allocation = allocate_course_slug(
                app,
                shifu_bid=shifu_bid,
                prepared=PreparedCourseSlug(base_slug, "llm"),
                claim_new_bid=True,
            )
            db.session.add(
                DraftShifu(
                    shifu_bid=shifu_bid,
                    title=f"Concurrent {shifu_bid}",
                    created_user_bid="mysql-concurrency-owner",
                    updated_user_bid="mysql-concurrency-owner",
                )
            )
            slug = str(allocation.binding.slug)
            db.session.commit()
            return {"ok": True, "bid": shifu_bid, "slug": slug}
        except ShifuIdentifierConflict as exc:
            db.session.rollback()
            return {
                "ok": False,
                "bid": shifu_bid,
                "error": type(exc).__name__,
            }
        finally:
            db.session.remove()


def _run_pair(*requests: tuple[str, str]) -> list[dict]:
    barrier = Barrier(len(requests))
    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        futures = [
            executor.submit(
                _allocate_course,
                barrier,
                shifu_bid=shifu_bid,
                base_slug=base_slug,
            )
            for shifu_bid, base_slug in requests
        ]
        return [future.result(timeout=40) for future in futures]


same_title = _run_pair(
    ("mysql-concurrent-title-one", "concurrent-course-public-link"),
    ("mysql-concurrent-title-two", "concurrent-course-public-link"),
)
assert all(result["ok"] for result in same_title), same_title
assert len({result["slug"] for result in same_title}) == 2, same_title

same_bid = _run_pair(
    ("mysql-concurrent-same-bid", "same-bid-course-public-link"),
    ("mysql-concurrent-same-bid", "same-bid-course-public-link"),
)
assert sum(bool(result["ok"]) for result in same_bid) == 1, same_bid
assert {result.get("slug") for result in same_bid if result["ok"]} == {
    "same-bid-course-public-link"
}, same_bid

shared_identifier = "shared-public-identifier"
cross_namespace = _run_pair(
    ("mysql-cross-namespace-course", shared_identifier),
    (shared_identifier, "independent-course-public-link"),
)
assert cross_namespace[0]["ok"], cross_namespace
assert any(result["ok"] for result in cross_namespace), cross_namespace

case_slug = "case-collision-course-link"
case_owner = _run_pair(("mysql-case-owner-course", case_slug))[0]
case_conflict = _run_pair(
    (case_slug.upper(), "case-conflict-alternate-link"),
)[0]
assert case_owner["ok"], case_owner
assert not case_conflict["ok"], case_conflict

symmetric_bid_barrier = Barrier(2)
symmetric_lock = Lock()
symmetric_claims = 0
original_reserve_course_bid = slug_module._reserve_course_bid


def _synchronize_first_symmetric_bid_claim(*args, **kwargs):
    global symmetric_claims
    reservation = original_reserve_course_bid(*args, **kwargs)
    with symmetric_lock:
        symmetric_claims += 1
        claim_number = symmetric_claims
    if claim_number <= 2:
        symmetric_bid_barrier.wait(timeout=20)
    return reservation


slug_module._reserve_course_bid = _synchronize_first_symmetric_bid_claim
try:
    symmetric_cross_namespace = _run_pair(
        ("symmetric-alpha-course-link", "symmetric-beta-course-link"),
        ("symmetric-beta-course-link", "symmetric-alpha-course-link"),
    )
finally:
    slug_module._reserve_course_bid = original_reserve_course_bid

assert sum(bool(result["ok"]) for result in symmetric_cross_namespace) == 1, (
    symmetric_cross_namespace
)
assert all(
    result["ok"] or result["error"] == "ShifuIdentifierConflict"
    for result in symmetric_cross_namespace
), symmetric_cross_namespace

with app.app_context():
    assert (
        ShifuCourseSlug.query.filter_by(
            shifu_bid="mysql-concurrent-same-bid",
            is_current=1,
        ).count()
        == 1
    )
    assert (
        DraftShifu.query.filter_by(shifu_bid="mysql-concurrent-same-bid").count() == 1
    )
    same_bid_reservations = ShifuPublicIdentifier.query.filter_by(
        shifu_bid="mysql-concurrent-same-bid"
    ).all()
    assert {(row.identifier, row.identifier_type) for row in same_bid_reservations} == {
        ("mysql-concurrent-same-bid", "bid"),
        ("same-bid-course-public-link", "slug"),
    }

    shared_rows = ShifuPublicIdentifier.query.filter_by(
        identifier=shared_identifier
    ).all()
    assert len(shared_rows) == 1
    shared = shared_rows[0]
    assert (shared.identifier_type, shared.shifu_bid) in {
        ("bid", shared_identifier),
        ("slug", "mysql-cross-namespace-course"),
    }
    expected_resolution = (
        shared_identifier
        if shared.identifier_type == "bid"
        else "mysql-cross-namespace-course"
    )
    assert resolve_shifu_identifier(app, shared_identifier) == expected_resolution

    result = {
        "same_title": same_title,
        "same_bid": same_bid,
        "cross_namespace": cross_namespace,
        "symmetric_cross_namespace": symmetric_cross_namespace,
        "case_insensitive_conflict": case_conflict,
        "shared_identifier_type": shared.identifier_type,
    }

print(json.dumps(result, sort_keys=True))
