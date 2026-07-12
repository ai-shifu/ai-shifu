from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from flaskr.dao import db
from flaskr.service.shifu.models import (
    DraftShifu,
    ShifuCourseSlug,
    ShifuPublicIdentifier,
)
from flaskr.service.shifu.slug import (
    PreparedCourseSlug,
    ShifuIdentifierConflict,
    allocate_course_slug,
    backfill_course_slugs,
    ensure_shifu_slug,
)
from flaskr.util.datetime import now_utc


def test_slug_allocation_reserves_bid_and_slug_in_one_namespace(app):
    course_bid = "namespace-reservation-course"
    slug = "atomic-course-public-link"

    with app.app_context():
        allocation = allocate_course_slug(
            app,
            shifu_bid=course_bid,
            prepared=PreparedCourseSlug(slug, "llm"),
        )
        db.session.commit()

        reservations = {
            (row.identifier, row.identifier_type, row.shifu_bid)
            for row in ShifuPublicIdentifier.query.filter_by(shifu_bid=course_bid).all()
        }
        assert allocation.binding.slug == slug
        assert reservations == {
            (course_bid, "bid", course_bid),
            (slug, "slug", course_bid),
        }


def test_committed_bid_reservation_forces_slug_collision_suffix(app):
    reserved_bid = "shared-public-identifier"
    target_bid = "namespace-collision-target"

    with app.app_context():
        db.session.add(
            ShifuPublicIdentifier(
                identifier=reserved_bid,
                shifu_bid=reserved_bid,
                identifier_type="bid",
            )
        )
        db.session.commit()

        allocation = allocate_course_slug(
            app,
            shifu_bid=target_bid,
            prepared=PreparedCourseSlug(reserved_bid, "llm"),
        )
        db.session.commit()

        assert allocation.collided is True
        assert allocation.binding.slug != reserved_bid
        assert allocation.binding.slug.startswith(f"{reserved_bid}-")


def test_new_bid_claim_allows_only_one_course_creator(app):
    course_bid = "single-creator-explicit-bid"
    prepared = PreparedCourseSlug("single-creator-course-link", "llm")

    with app.app_context():
        winner = allocate_course_slug(
            app,
            shifu_bid=course_bid,
            prepared=prepared,
            claim_new_bid=True,
        )
        db.session.add(
            DraftShifu(
                shifu_bid=course_bid,
                title="Winning creator",
                created_user_bid="owner",
                updated_user_bid="owner",
            )
        )
        db.session.commit()

        with pytest.raises(ShifuIdentifierConflict, match="already exists"):
            allocate_course_slug(
                app,
                shifu_bid=course_bid,
                prepared=prepared,
                claim_new_bid=True,
            )

        assert winner.created is True
        assert DraftShifu.query.filter_by(shifu_bid=course_bid).count() == 1


def test_legacy_bid_precedence_repairs_shadowing_slug_reservation(app, monkeypatch):
    slug_owner_bid = "legacy-shadowed-slug-owner"
    legacy_bid = "legacy-bid-always-wins"
    owner_slug = legacy_bid
    legacy_course_slug = "legacy-bid-course-link"

    with app.app_context():
        db.session.add_all(
            [
                DraftShifu(
                    shifu_bid=slug_owner_bid,
                    title="Slug owner",
                    created_user_bid="owner",
                    updated_user_bid="owner",
                ),
                DraftShifu(
                    shifu_bid=legacy_bid,
                    title="Legacy BID owner",
                    created_user_bid="owner",
                    updated_user_bid="owner",
                ),
                ShifuCourseSlug(
                    shifu_bid=slug_owner_bid,
                    slug=owner_slug,
                    version=1,
                    is_current=1,
                    generation_source="llm",
                ),
            ]
        )
        db.session.commit()

        selected = ensure_shifu_slug(
            app,
            shifu_bid=slug_owner_bid,
            title="Slug owner",
        )
        db.session.commit()

        shared = ShifuPublicIdentifier.query.filter_by(identifier=legacy_bid).one()
        assert selected.slug == owner_slug
        assert (shared.identifier_type, shared.shifu_bid) == ("bid", legacy_bid)

        monkeypatch.setattr(
            "flaskr.service.shifu.slug.prepare_course_slug",
            lambda *_args, **_kwargs: PreparedCourseSlug(
                legacy_course_slug,
                "llm",
            ),
        )
        legacy_binding = ensure_shifu_slug(
            app,
            shifu_bid=legacy_bid,
            title="Legacy BID owner",
        )
        db.session.commit()

        assert legacy_binding.slug == legacy_course_slug
        shared = ShifuPublicIdentifier.query.filter_by(identifier=legacy_bid).one()
        assert (shared.identifier_type, shared.shifu_bid) == ("bid", legacy_bid)


def test_existing_slug_lazily_backfills_identifier_reservations(app, monkeypatch):
    course_bid = "legacy-slug-reservation-course"
    slug = "legacy-course-public-link"

    with app.app_context():
        binding = ShifuCourseSlug(
            shifu_bid=course_bid,
            slug=slug,
            version=1,
            is_current=1,
            generation_source="llm",
        )
        db.session.add(binding)
        db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.shifu.slug.prepare_course_slug",
            lambda *_args, **_kwargs: pytest.fail("existing slug must not regenerate"),
        )
        selected = ensure_shifu_slug(app, shifu_bid=course_bid, title="Renamed")
        db.session.commit()

        assert selected.id == binding.id
        assert {
            row.identifier: row.identifier_type
            for row in ShifuPublicIdentifier.query.filter_by(shifu_bid=course_bid).all()
        } == {course_bid: "bid", slug: "slug"}


def test_backfill_reconciles_current_and_historical_reservations_idempotently(
    app, monkeypatch
):
    from flaskr.service.shifu import slug as slug_module

    course_bid = "reservation-history-backfill"
    historical_slug = "historical-reservation-link"
    current_slug = "current-reservation-course-link"

    with app.app_context():
        db.session.add_all(
            [
                DraftShifu(
                    shifu_bid=course_bid,
                    title="Existing versioned slug course",
                    created_user_bid="owner",
                    updated_user_bid="owner",
                ),
                ShifuCourseSlug(
                    shifu_bid=course_bid,
                    slug=historical_slug,
                    version=1,
                    is_current=None,
                    generation_source="manual",
                    retired_at=now_utc(),
                ),
                ShifuCourseSlug(
                    shifu_bid=course_bid,
                    slug=current_slug,
                    version=2,
                    is_current=1,
                    generation_source="manual",
                ),
            ]
        )
        db.session.commit()
        monkeypatch.setattr(
            "flaskr.service.shifu.slug.prepare_course_slug",
            lambda *_args, **_kwargs: pytest.fail(
                "reservation reconciliation must not regenerate the slug"
            ),
        )
        real_reserve = slug_module._reserve_public_identifier
        injected_failure = False

        def fail_historical_reservation_once(**kwargs):
            nonlocal injected_failure
            if kwargs["identifier"] == historical_slug and not injected_failure:
                injected_failure = True
                raise RuntimeError("injected reservation failure")
            return real_reserve(**kwargs)

        monkeypatch.setattr(
            slug_module,
            "_reserve_public_identifier",
            fail_historical_reservation_once,
        )

        first = backfill_course_slugs(app, shifu_bid=course_bid, batch_size=1)
        db.session.remove()
        first_rows = {
            (row.identifier, row.identifier_type, row.shifu_bid)
            for row in ShifuPublicIdentifier.query.filter_by(shifu_bid=course_bid).all()
        }
        second = backfill_course_slugs(app, shifu_bid=course_bid, batch_size=1)
        db.session.remove()
        second_rows = {
            (row.identifier, row.identifier_type, row.shifu_bid)
            for row in ShifuPublicIdentifier.query.filter_by(shifu_bid=course_bid).all()
        }
        third = backfill_course_slugs(app, shifu_bid=course_bid, batch_size=1)
        db.session.remove()
        third_rows = {
            (row.identifier, row.identifier_type, row.shifu_bid)
            for row in ShifuPublicIdentifier.query.filter_by(shifu_bid=course_bid).all()
        }

        expected = {
            (course_bid, "bid", course_bid),
            (historical_slug, "slug", course_bid),
            (current_slug, "slug", course_bid),
        }
        assert first["existing"] == 1
        assert first["failed"] == 1
        assert first_rows == set()
        assert second["existing"] == 1
        assert second["failed"] == 0
        assert third["existing"] == 1
        assert third["failed"] == 0
        assert second_rows == expected
        assert third_rows == expected


def test_allocator_retries_mysql_deadlock_with_same_prepared_slug(app, monkeypatch):
    from flaskr.service.shifu import slug as slug_module

    prepared = PreparedCourseSlug("deadlock-retry-course-link", "llm")
    real_allocate_once = slug_module._allocate_course_slug_once
    seen_prepared: list[PreparedCourseSlug] = []

    def deadlock_once(**kwargs):
        seen_prepared.append(kwargs["prepared"])
        if len(seen_prepared) == 1:
            raise OperationalError(
                "INSERT",
                {},
                Exception(1213, "Deadlock found when trying to get lock"),
            )
        return real_allocate_once(**kwargs)

    monkeypatch.setattr(slug_module, "_allocate_course_slug_once", deadlock_once)
    monkeypatch.setattr(
        slug_module,
        "_is_retryable_mysql_operational_error",
        lambda _exc: True,
    )

    with app.app_context():
        db.session.query(DraftShifu.id).first()
        assert db.session().in_transaction()
        allocation = allocate_course_slug(
            app,
            shifu_bid="deadlock-retry-course",
            prepared=prepared,
            claim_new_bid=True,
        )
        db.session.commit()

        assert allocation.binding.slug == prepared.base_slug
        assert seen_prepared == [prepared, prepared]


def test_allocator_does_not_retry_deadlock_with_staged_course_writes(app, monkeypatch):
    from flaskr.service.shifu import slug as slug_module

    attempts = 0

    def always_deadlocks(**_kwargs):
        nonlocal attempts
        attempts += 1
        raise OperationalError(
            "INSERT",
            {},
            Exception(1213, "Deadlock found when trying to get lock"),
        )

    monkeypatch.setattr(slug_module, "_allocate_course_slug_once", always_deadlocks)
    monkeypatch.setattr(
        slug_module,
        "_is_retryable_mysql_operational_error",
        lambda _exc: True,
    )

    with app.app_context():
        staged = DraftShifu(
            shifu_bid="staged-deadlock-course",
            title="Staged before allocation",
            created_user_bid="owner",
            updated_user_bid="owner",
        )
        db.session.add(staged)

        with pytest.raises(OperationalError):
            allocate_course_slug(
                app,
                shifu_bid="staged-deadlock-course",
                prepared=PreparedCourseSlug("staged-deadlock-course-link", "llm"),
                claim_new_bid=True,
            )

        assert attempts == 1
        assert staged in db.session.new
        db.session.rollback()


def test_identifier_reservations_roll_back_with_course_creation(app):
    course_bid = "rollback-namespace-course"
    slug = "rollback-course-public-link"

    with app.app_context():
        allocate_course_slug(
            app,
            shifu_bid=course_bid,
            prepared=PreparedCourseSlug(slug, "llm"),
        )
        db.session.add(
            DraftShifu(
                shifu_bid=course_bid,
                title="Rollback course",
                created_user_bid="owner",
                updated_user_bid="owner",
            )
        )
        db.session.flush()
        db.session.rollback()

        assert ShifuCourseSlug.query.filter_by(shifu_bid=course_bid).first() is None
        assert (
            ShifuPublicIdentifier.query.filter_by(shifu_bid=course_bid).first() is None
        )
        assert DraftShifu.query.filter_by(shifu_bid=course_bid).first() is None


@pytest.mark.parametrize(
    ("identifier", "shifu_bid", "identifier_type"),
    [
        ("invalid-type-course-link", "invalid-type-course", "other"),
        ("different-public-bid", "canonical-public-bid", "bid"),
    ],
)
def test_identifier_reservation_constraints_reject_invalid_rows(
    app,
    identifier,
    shifu_bid,
    identifier_type,
):
    with app.app_context():
        db.session.add(
            ShifuPublicIdentifier(
                identifier=identifier,
                shifu_bid=shifu_bid,
                identifier_type=identifier_type,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
