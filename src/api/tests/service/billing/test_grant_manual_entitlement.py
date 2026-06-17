from __future__ import annotations

import flaskr.dao as dao


def _cleanup(app, creator_bid: str) -> None:
    from flaskr.service.billing.models import BillingEntitlement

    with app.app_context():
        BillingEntitlement.query.filter_by(creator_bid=creator_bid).delete()
        dao.db.session.commit()


def test_grant_manual_entitlement_is_immediately_active(app):
    """A freshly granted manual entitlement must resolve as active right away.

    Regression guard for the same-second race: effective_from is back-dated so
    a resolve() running microseconds after the insert still sees the snapshot
    (MySQL DATETIME rounds sub-second values, which previously could push
    effective_from just past the resolve timestamp and miss the row).
    """
    from flaskr.service.billing.entitlements import (
        grant_creator_manual_entitlement,
        resolve_creator_entitlement_state,
    )

    creator_bid = "grant-immediate-active-test"
    _cleanup(app, creator_bid)
    try:
        with app.app_context():
            state = grant_creator_manual_entitlement(
                app,
                creator_bid,
                branding_enabled=True,
                custom_domain_enabled=True,
                branding={"logo_wide_url": "https://cdn.example.com/wide.png"},
            )
            assert state.branding_enabled is True
            assert state.custom_domain_enabled is True

            # Independent re-resolution must also see it as active.
            again = resolve_creator_entitlement_state(creator_bid)
            assert again.branding_enabled is True
            assert again.custom_domain_enabled is True
            assert again.source_kind == "snapshot"
    finally:
        _cleanup(app, creator_bid)
