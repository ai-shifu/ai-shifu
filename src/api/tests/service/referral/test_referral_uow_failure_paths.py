"""Unit-of-work behavior for the B4 referral call sites."""

from __future__ import annotations

from datetime import datetime

from flaskr.dao import db, uow
from flaskr.service.referral import service as referral_service
from flaskr.service.referral.consts import (
    REFERRAL_INVITE_CODE_STATUS_ACTIVE,
    REFERRAL_RELATION_STATUS_REWARD_GENERATED,
)
from flaskr.service.referral.models import (
    ReferralInviteCode,
    ReferralInviteRelation,
    ReferralInviteReward,
)
from flaskr.service.referral.service import (
    build_invite_profile,
    process_referral_post_auth,
)
from flaskr.service.user.post_auth import PostAuthContext

from tests.service.referral.test_referral_service import _seed_campaign


def _seed_invite_code(campaign_bid: str, *, code: str, inviter: str) -> None:
    db.session.add(
        ReferralInviteCode(
            invite_code_bid=f"code-{code}",
            campaign_bid=campaign_bid,
            inviter_user_bid=inviter,
            invite_code=code,
            status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
            generated_at=datetime(2026, 6, 9, 12, 0, 0),
        )
    )
    db.session.commit()


def test_invite_code_collision_is_retried_inside_the_callers_unit_of_work(
    referral_app: object, monkeypatch: object
) -> None:
    """The savepoint keeps a duplicate code local: the outer transaction survives."""
    with referral_app.app_context():
        campaign, _rule = _seed_campaign(campaign_bid="ref-campaign-collide")
        _seed_invite_code(
            campaign.campaign_bid, code="TAKEN001", inviter="someone-else"
        )
        monkeypatch.setattr(
            referral_service,
            "_resolve_public_origin",
            lambda: "https://frontend.example",
        )
        codes = iter(["TAKEN001", "FRESH002"])
        monkeypatch.setattr(
            referral_service, "_generate_invite_code", lambda: next(codes)
        )

        profile = build_invite_profile(referral_app, inviter_user_bid="inviter-collide")

        assert profile.invite_code == "FRESH002"
        rows = ReferralInviteCode.query.filter_by(
            inviter_user_bid="inviter-collide"
        ).all()
        assert [row.invite_code for row in rows] == ["FRESH002"]


def test_post_auth_grant_failure_keeps_relation_and_marks_reward_failed(
    referral_app: object, monkeypatch: object
) -> None:
    """Step 1 (relation + reward) is durable even when step 2 (billing grant) fails."""
    with referral_app.app_context():
        campaign, _rule = _seed_campaign(campaign_bid="ref-campaign-uow-fail")
        _seed_invite_code(
            campaign.campaign_bid, code="UOWFAIL1", inviter="inviter-uow-fail"
        )
        monkeypatch.setattr(
            referral_service,
            "_load_invitee_mobile_snapshot",
            lambda _bid: "15500009999",
        )

        def failing_grant(_app: object, *, reward: object) -> dict:
            # Stage a write that must be rolled back with the failed step.
            reward.rule_snapshot = {"tainted": True}
            db.session.add(reward)
            db.session.flush()
            message = "billing offline"
            raise RuntimeError(message)

        monkeypatch.setattr(
            referral_service, "grant_referral_plan_reward", failing_grant
        )

        result = process_referral_post_auth(
            referral_app,
            PostAuthContext(
                user_id="invitee-uow-fail",
                source="sms",
                created_new_user=True,
                invite_code="UOWFAIL1",
            ),
        )

        assert result.skipped_reason == "billing_grant_failed"
        db.session.expire_all()
        relation = ReferralInviteRelation.query.filter_by(
            invitee_user_bid="invitee-uow-fail"
        ).one()
        reward = ReferralInviteReward.query.filter_by(
            relation_bid=relation.relation_bid
        ).one()
        assert relation.relation_status != REFERRAL_RELATION_STATUS_REWARD_GENERATED
        assert reward.billing_artifacts["grant_error"] == "billing offline"
        # The tainted snapshot staged inside the failed step did not persist.
        assert reward.rule_snapshot != {"tainted": True}
        assert not uow.in_unit_of_work()
