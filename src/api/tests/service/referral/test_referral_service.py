from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from flask import Flask, request

from flaskr.dao import db
from flaskr.service.referral.routes import register_referral_routes
from flaskr.service.referral.consts import (
    REFERRAL_CAMPAIGN_STATUS_ACTIVE,
    REFERRAL_INVITE_CODE_STATUS_ACTIVE,
    REFERRAL_INVITE_EVENT_CODE_ENTERED,
    REFERRAL_RELATION_STATUS_REGISTERED,
    REFERRAL_RELATION_STATUS_REWARD_GENERATED,
    REFERRAL_RELATION_STATUS_REWARD_SKIPPED_CAP,
    REFERRAL_REWARD_STATUS_GENERATED,
    REFERRAL_REWARD_STATUS_PENDING_EFFECTIVE,
    REFERRAL_REWARD_STATUS_SKIPPED_CAP,
    REFERRAL_REWARD_TARGET_INVITER,
    REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
    REFERRAL_RULE_STATUS_ACTIVE,
    REFERRAL_TRIGGER_INVITED_REGISTRATION,
)
from flaskr.service.referral.models import (
    ReferralCampaign,
    ReferralCampaignRewardRule,
    ReferralInviteCode,
    ReferralInviteEvent,
    ReferralInviteRelation,
    ReferralInviteReward,
)
from flaskr.service.referral.service import (
    InviteEventInput,
    build_invite_profile,
    load_active_campaign,
    mask_identifier_snapshot,
    process_referral_post_auth,
    record_invite_event,
    retry_pending_referral_rewards,
)
from flaskr.service.user.post_auth import PostAuthContext
from flaskr.service.user.models import UserInfo as UserEntity


def _seed_campaign(
    *,
    campaign_bid: str = "ref-campaign-service",
    campaign_code: str = "domestic_creator_invite_202606_service",
    feature_flag_key: str = "",
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    cap_count: int = 12,
) -> tuple[ReferralCampaign, ReferralCampaignRewardRule]:
    campaign = ReferralCampaign(
        campaign_bid=campaign_bid,
        campaign_code=campaign_code,
        campaign_name="Domestic creator invite",
        campaign_status=REFERRAL_CAMPAIGN_STATUS_ACTIVE,
        feature_flag_key=feature_flag_key,
        starts_at=starts_at,
        ends_at=ends_at,
        invite_route_template="/invite/{invite_code}",
        inviter_eligibility={"registered_phone_user": True},
        invitee_eligibility={"created_new_phone_user": True},
        invitee_benefit_policy="existing_trial_only",
        rules_copy_i18n_key="module.referral.rules.domesticCreatorInvite",
        metadata_json={},
    )
    rule = ReferralCampaignRewardRule(
        reward_rule_bid=f"{campaign_bid}-rule",
        campaign_bid=campaign_bid,
        rule_code="inviter_monthly_pro_first_12",
        rule_status=REFERRAL_RULE_STATUS_ACTIVE,
        trigger_event=REFERRAL_TRIGGER_INVITED_REGISTRATION,
        reward_target=REFERRAL_REWARD_TARGET_INVITER,
        reward_type=REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
        reward_product_code="creator-plan-monthly-pro",
        reward_cycle_count=1,
        reward_credit_amount=Decimal("1000.0000000000"),
        reward_credit_validity_days=30,
        reward_cap_scope="per_inviter",
        reward_cap_count=cap_count,
        reward_timing_policy="immediate_extend_or_defer",
        priority=10,
        metadata_json={"expected_price_amount": 19900},
    )
    db.session.add_all([campaign, rule])
    db.session.commit()
    return campaign, rule


def test_load_active_campaign_honors_window_and_feature_flag(
    referral_app,
    monkeypatch,
) -> None:
    with referral_app.app_context():
        now = datetime(2026, 6, 9, 12, 0, 0)
        _seed_campaign(
            campaign_bid="ref-campaign-flagged",
            campaign_code="domestic_creator_invite_flagged",
            feature_flag_key="REFERRAL_INVITE_REWARDS_ENABLED",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )

        monkeypatch.setattr(
            "flaskr.service.referral.service.get_common_config",
            lambda key, default=None: (
                "0" if key == "REFERRAL_INVITE_REWARDS_ENABLED" else default
            ),
        )
        assert load_active_campaign(now=now) is None

        monkeypatch.setattr(
            "flaskr.service.referral.service.get_common_config",
            lambda key, default=None: (
                "true" if key == "REFERRAL_INVITE_REWARDS_ENABLED" else default
            ),
        )
        assert load_active_campaign(now=now).campaign_code == (
            "domestic_creator_invite_flagged"
        )


def test_invite_profile_lazily_creates_stable_campaign_scoped_code(
    referral_app,
    monkeypatch,
) -> None:
    with referral_app.app_context():
        _seed_campaign(campaign_bid="ref-campaign-profile")
        monkeypatch.setattr(
            "flaskr.service.referral.service._resolve_public_origin",
            lambda: "https://frontend.example",
        )

        first = build_invite_profile(referral_app, inviter_user_bid="inviter-profile-1")
        second = build_invite_profile(
            referral_app, inviter_user_bid="inviter-profile-1"
        )

        assert first.invite_code == second.invite_code
        assert first.invite_url == second.invite_url
        assert (
            first.invite_url == f"https://frontend.example/invite/{first.invite_code}"
        )
        assert first.reward_cap_count == 12
        assert first.reward_granted_count == 0
        assert first.reward_remaining_count == 12


def test_invite_profile_route_returns_unavailable_without_campaign(
    referral_app,
) -> None:
    register_referral_routes(referral_app, "/api/referral")

    @referral_app.before_request
    def _inject_request_user() -> None:
        request.user = SimpleNamespace(user_id="inviter-no-campaign")

    response = referral_app.test_client().get("/api/referral/invite-profile")
    payload = response.get_json(force=True)["data"]

    assert response.status_code == 200
    assert payload == {
        "available": False,
        "campaign_bid": "",
        "campaign_code": "",
        "invite_code": "",
        "invite_url": "",
        "reward_product_code": "",
        "reward_cycle_count": 0,
        "reward_credit_amount": None,
        "reward_credit_validity_days": None,
        "reward_cap_scope": "",
        "reward_cap_count": None,
        "reward_granted_count": 0,
        "reward_remaining_count": None,
        "reward_queue_summary": {},
        "reward_queue": [],
        "rules_copy_i18n_key": "",
    }
    assert ReferralInviteCode.query.count() == 0


def test_invite_profile_route_returns_unavailable_without_reward_rule(
    referral_app,
) -> None:
    register_referral_routes(referral_app, "/api/referral")

    @referral_app.before_request
    def _inject_request_user() -> None:
        request.user = SimpleNamespace(user_id="inviter-no-rule")

    with referral_app.app_context():
        _campaign, rule = _seed_campaign(campaign_bid="ref-campaign-no-rule")
        rule.deleted = 1
        db.session.commit()

    response = referral_app.test_client().get("/api/referral/invite-profile")
    payload = response.get_json(force=True)["data"]

    assert response.status_code == 200
    assert payload["available"] is False
    assert payload["campaign_bid"] == ""
    assert payload["invite_url"] == ""
    assert ReferralInviteCode.query.count() == 0


def test_invite_profile_includes_creator_reward_queue(
    referral_app,
    monkeypatch,
) -> None:
    with referral_app.app_context():
        campaign, rule = _seed_campaign(campaign_bid="ref-campaign-profile-queue")
        inviter_user_bid = "inviter-profile-queue"
        relation = ReferralInviteRelation(
            relation_bid="relation-profile-queue",
            campaign_bid=campaign.campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            invite_code="QUEUE123",
            inviter_user_bid=inviter_user_bid,
            invitee_user_bid="invitee-profile-queue",
            invitee_mobile_snapshot="13521510781",
            bound_at=datetime(2026, 6, 11, 12, 0, 0),
            registration_source="phone",
            reward_eligible=True,
            relation_status=REFERRAL_RELATION_STATUS_REWARD_GENERATED,
            metadata_json={},
        )
        reward = ReferralInviteReward(
            reward_bid="reward-profile-queue",
            campaign_bid=campaign.campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            relation_bid=relation.relation_bid,
            inviter_user_bid=inviter_user_bid,
            invitee_user_bid=relation.invitee_user_bid,
            reward_status=REFERRAL_REWARD_STATUS_PENDING_EFFECTIVE,
            reward_target=REFERRAL_REWARD_TARGET_INVITER,
            reward_type=REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
            reward_product_code=rule.reward_product_code,
            reward_cycle_count=rule.reward_cycle_count,
            reward_credit_amount=rule.reward_credit_amount,
            reward_credit_validity_days=rule.reward_credit_validity_days,
            reward_cap_scope=rule.reward_cap_scope,
            reward_cap_count=rule.reward_cap_count,
            reward_timing_policy=rule.reward_timing_policy,
            rule_snapshot={},
            billing_artifacts={},
            effective_at=datetime(2026, 6, 26, 13, 18, 0),
            expires_at=datetime(2026, 7, 26, 13, 18, 0),
        )
        db.session.add_all([relation, reward])
        db.session.commit()
        monkeypatch.setattr(
            "flaskr.service.referral.service._resolve_public_origin",
            lambda: "https://frontend.example",
        )

        profile = build_invite_profile(
            referral_app,
            inviter_user_bid=inviter_user_bid,
        )

        queue = profile.to_dict()["reward_queue"]
        assert queue == [
            {
                "queue_index": 1,
                "reward_bid": "reward-profile-queue",
                "relation_bid": "relation-profile-queue",
                "invitee_mobile_snapshot": "135****0781",
                "reward_status": REFERRAL_REWARD_STATUS_PENDING_EFFECTIVE,
                "reward_credit_amount": "1000.0000000000",
                "reward_product_code": "creator-plan-monthly-pro",
                "ledger_credit_state": "",
                "effective_at": "2026-06-26T13:18:00Z",
                "expires_at": "2026-07-26T13:18:00Z",
                "created_at": reward.created_at.isoformat() + "Z",
            }
        ]
        assert "13521510781" not in str(queue)


def test_invite_preview_route_returns_only_masked_inviter_mobile(
    referral_app,
) -> None:
    register_referral_routes(referral_app, "/api/referral")
    with referral_app.app_context():
        campaign, _rule = _seed_campaign(campaign_bid="ref-campaign-preview")
        db.session.add_all(
            [
                UserEntity(
                    user_bid="inviter-preview",
                    user_identify="15512340064",
                    nickname="Private inviter name",
                ),
                ReferralInviteCode(
                    invite_code_bid="ref-code-preview",
                    campaign_bid=campaign.campaign_bid,
                    inviter_user_bid="inviter-preview",
                    invite_code="PREVIEW1",
                    status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
                ),
            ]
        )
        db.session.commit()

    response = referral_app.test_client().get(
        "/api/referral/invite-preview?invite_code=preview1"
    )
    payload = response.get_json(force=True)["data"]

    assert response.status_code == 200
    assert payload == {
        "recognized": True,
        "invite_code": "PREVIEW1",
        "inviter_mobile_masked": "155****0064",
    }
    assert "15512340064" not in str(payload)
    assert "inviter-preview" not in str(payload)
    assert "Private inviter name" not in str(payload)


def test_invite_preview_route_masks_email_inviter_identifier(
    referral_app,
) -> None:
    register_referral_routes(referral_app, "/api/referral")
    with referral_app.app_context():
        campaign, _rule = _seed_campaign(campaign_bid="ref-campaign-preview-email")
        db.session.add_all(
            [
                UserEntity(
                    user_bid="inviter-preview-email",
                    user_identify="teacher@example.com",
                    nickname="Private email inviter",
                ),
                ReferralInviteCode(
                    invite_code_bid="ref-code-preview-email",
                    campaign_bid=campaign.campaign_bid,
                    inviter_user_bid="inviter-preview-email",
                    invite_code="MAIL1234",
                    status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
                ),
            ]
        )
        db.session.commit()

    response = referral_app.test_client().get(
        "/api/referral/invite-preview?invite_code=mail1234"
    )
    payload = response.get_json(force=True)["data"]

    assert response.status_code == 200
    assert payload == {
        "recognized": True,
        "invite_code": "MAIL1234",
        "inviter_mobile_masked": "te****r@example.com",
    }
    assert "teacher@example.com" not in str(payload)
    assert "inviter-preview-email" not in str(payload)
    assert "Private email inviter" not in str(payload)


def test_mask_identifier_snapshot_handles_phone_email_and_short_values() -> None:
    assert mask_identifier_snapshot("15512340064") == "155****0064"
    assert mask_identifier_snapshot("+86 15512340064") == "155****0064"
    assert mask_identifier_snapshot("teacher@example.com") == "te****r@example.com"
    assert mask_identifier_snapshot("a@example.com") == "a****@example.com"
    assert mask_identifier_snapshot("not-identifying") == "****"
    assert mask_identifier_snapshot("") == ""


def test_invite_preview_route_is_non_identifying_for_unknown_code(
    referral_app,
) -> None:
    register_referral_routes(referral_app, "/api/referral")

    response = referral_app.test_client().get(
        "/api/referral/invite-preview?invite_code=missing"
    )
    payload = response.get_json(force=True)["data"]

    assert response.status_code == 200
    assert payload == {
        "recognized": False,
        "invite_code": "",
        "inviter_mobile_masked": "",
    }


def test_record_invite_event_hashes_client_context(referral_app) -> None:
    with referral_app.app_context():
        campaign, _rule = _seed_campaign(campaign_bid="ref-campaign-event")
        db.session.add(
            ReferralInviteCode(
                invite_code_bid="ref-code-event-1",
                campaign_bid=campaign.campaign_bid,
                inviter_user_bid="inviter-event-1",
                invite_code="EVT12345",
                status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
                generated_at=datetime(2026, 6, 9, 12, 0, 0),
            )
        )
        db.session.commit()

        result = record_invite_event(
            referral_app,
            InviteEventInput(
                event_type=REFERRAL_INVITE_EVENT_CODE_ENTERED,
                invite_code="EVT12345",
                landing_path="/signup",
                session_id="",
                entry_source="manual",
                client_ip="203.0.113.10",
                user_agent="Mozilla/5.0 referral-test",
            ),
        )

        assert result.success is True
        assert result.session_id

        event = ReferralInviteEvent.query.filter_by(invite_code="EVT12345").one()
        assert event.client_ip_hash
        assert event.user_agent_hash
        assert event.client_ip_hash != "203.0.113.10"
        assert event.user_agent_hash != "Mozilla/5.0 referral-test"
        assert event.metadata_json["entry_source"] == "manual"


def test_post_auth_binding_is_idempotent_and_creates_reward(
    referral_app,
    monkeypatch,
) -> None:
    grant_calls: list[str] = []

    with referral_app.app_context():
        campaign, _rule = _seed_campaign(campaign_bid="ref-campaign-post-auth")
        db.session.add(
            ReferralInviteCode(
                invite_code_bid="ref-code-post-auth-1",
                campaign_bid=campaign.campaign_bid,
                inviter_user_bid="inviter-post-auth-1",
                invite_code="POSTAUTH1",
                status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
                generated_at=datetime(2026, 6, 9, 12, 0, 0),
            )
        )
        db.session.commit()

        def fake_grant(_app: Flask, *, reward: ReferralInviteReward):
            grant_calls.append(reward.reward_bid)
            reward.reward_status = REFERRAL_REWARD_STATUS_GENERATED
            reward.billing_artifacts = {
                "subscription_bid": "sub-post-auth",
                "bill_order_bid": "order-post-auth",
            }
            return reward.billing_artifacts

        monkeypatch.setattr(
            "flaskr.service.referral.service.grant_referral_plan_reward",
            fake_grant,
        )
        monkeypatch.setattr(
            "flaskr.service.referral.service._load_invitee_mobile_snapshot",
            lambda _user_bid: "15500002222",
        )

        context = PostAuthContext(
            user_id="invitee-post-auth-1",
            source="sms",
            created_new_user=True,
            invite_code="POSTAUTH1",
            referral_session_id="session-post-auth",
            referral_entry_source="link",
        )

        first = process_referral_post_auth(referral_app, context)
        second = process_referral_post_auth(referral_app, replace(context))

        assert first.created_relation is True
        assert first.created_reward is True
        assert second.created_relation is False
        assert second.created_reward is False
        assert len(grant_calls) == 1

        relation = ReferralInviteRelation.query.filter_by(
            invitee_user_bid="invitee-post-auth-1"
        ).one()
        assert relation.relation_status == REFERRAL_RELATION_STATUS_REWARD_GENERATED
        assert relation.metadata_json["referral_session_id"] == "session-post-auth"
        assert (
            ReferralInviteReward.query.filter_by(relation_bid=relation.relation_bid)
            .one()
            .billing_artifacts["bill_order_bid"]
            == "order-post-auth"
        )


def test_post_auth_preserves_reward_when_billing_grant_fails_then_repairs(
    referral_app,
    monkeypatch,
) -> None:
    with referral_app.app_context():
        campaign, _rule = _seed_campaign(campaign_bid="ref-campaign-repair")
        db.session.add(
            ReferralInviteCode(
                invite_code_bid="ref-code-repair-1",
                campaign_bid=campaign.campaign_bid,
                inviter_user_bid="inviter-repair-1",
                invite_code="REPAIR01",
                status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
                generated_at=datetime(2026, 6, 9, 12, 0, 0),
            )
        )
        db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.referral.service.grant_referral_plan_reward",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("billing offline")
            ),
        )
        monkeypatch.setattr(
            "flaskr.service.referral.service._load_invitee_mobile_snapshot",
            lambda _user_bid: "15500004444",
        )

        result = process_referral_post_auth(
            referral_app,
            PostAuthContext(
                user_id="invitee-repair-1",
                source="sms",
                created_new_user=True,
                invite_code="REPAIR01",
            ),
        )

        assert result.skipped_reason == "billing_grant_failed"
        relation = ReferralInviteRelation.query.filter_by(
            invitee_user_bid="invitee-repair-1"
        ).one()
        reward = ReferralInviteReward.query.filter_by(
            relation_bid=relation.relation_bid
        ).one()
        assert relation.relation_status == REFERRAL_RELATION_STATUS_REGISTERED
        assert reward.billing_artifacts["grant_error"] == "billing offline"

        dry_run = retry_pending_referral_rewards(referral_app, dry_run=True)
        assert dry_run == [
            {
                "reward_bid": reward.reward_bid,
                "relation_bid": relation.relation_bid,
                "action": "would_retry",
            }
        ]

        monkeypatch.setattr(
            "flaskr.service.referral.service.grant_referral_plan_reward",
            lambda _app, *, reward: {
                "subscription_bid": "sub-repaired",
                "bill_order_bid": f"order-{reward.reward_bid}",
                "wallet_bucket_bid": "bucket-repaired",
                "ledger_bid": "ledger-repaired",
            },
        )

        repaired = retry_pending_referral_rewards(referral_app, dry_run=False)

        assert repaired[0]["action"] == "retried"
        db.session.expire_all()
        assert (
            ReferralInviteRelation.query.filter_by(relation_bid=relation.relation_bid)
            .one()
            .relation_status
            == REFERRAL_RELATION_STATUS_REWARD_GENERATED
        )
        assert (
            ReferralInviteReward.query.filter_by(reward_bid=reward.reward_bid)
            .one()
            .billing_artifacts["bill_order_bid"]
            == f"order-{reward.reward_bid}"
        )


def test_post_auth_binding_marks_cap_skipped_without_billing_side_effect(
    referral_app,
    monkeypatch,
) -> None:
    with referral_app.app_context():
        campaign, rule = _seed_campaign(
            campaign_bid="ref-campaign-cap",
            cap_count=1,
        )
        db.session.add(
            ReferralInviteCode(
                invite_code_bid="ref-code-cap-1",
                campaign_bid=campaign.campaign_bid,
                inviter_user_bid="inviter-cap-1",
                invite_code="CAP00001",
                status=REFERRAL_INVITE_CODE_STATUS_ACTIVE,
                generated_at=datetime(2026, 6, 9, 12, 0, 0),
            )
        )
        existing_relation = ReferralInviteRelation(
            relation_bid="ref-relation-cap-existing",
            campaign_bid=campaign.campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            invite_code="CAP00001",
            inviter_user_bid="inviter-cap-1",
            invitee_user_bid="invitee-cap-existing",
            invitee_mobile_snapshot="15500001111",
            bound_at=datetime(2026, 6, 9, 12, 1, 0),
            registration_source="phone",
            reward_eligible=1,
            relation_status=REFERRAL_RELATION_STATUS_REWARD_GENERATED,
        )
        existing_reward = ReferralInviteReward(
            reward_bid="ref-reward-cap-existing",
            campaign_bid=campaign.campaign_bid,
            reward_rule_bid=rule.reward_rule_bid,
            relation_bid=existing_relation.relation_bid,
            inviter_user_bid="inviter-cap-1",
            invitee_user_bid="invitee-cap-existing",
            reward_status=REFERRAL_REWARD_STATUS_GENERATED,
            reward_target=REFERRAL_REWARD_TARGET_INVITER,
            reward_type=REFERRAL_REWARD_TYPE_BILLING_PLAN_CYCLE,
            reward_product_code=rule.reward_product_code,
            reward_cycle_count=rule.reward_cycle_count,
            reward_credit_amount=rule.reward_credit_amount,
            reward_credit_validity_days=rule.reward_credit_validity_days,
            reward_cap_scope=rule.reward_cap_scope,
            reward_cap_count=rule.reward_cap_count,
            reward_timing_policy=rule.reward_timing_policy,
            rule_snapshot=rule.to_snapshot(),
        )
        db.session.add_all([existing_relation, existing_reward])
        db.session.commit()

        monkeypatch.setattr(
            "flaskr.service.referral.service.grant_referral_plan_reward",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("billing grant should not run when cap is reached")
            ),
        )
        monkeypatch.setattr(
            "flaskr.service.referral.service._load_invitee_mobile_snapshot",
            lambda _user_bid: "15500003333",
        )

        result = process_referral_post_auth(
            referral_app,
            PostAuthContext(
                user_id="invitee-cap-new",
                source="sms",
                created_new_user=True,
                invite_code="CAP00001",
            ),
        )

        assert result.created_relation is True
        assert result.created_reward is True

        relation = ReferralInviteRelation.query.filter_by(
            invitee_user_bid="invitee-cap-new"
        ).one()
        reward = ReferralInviteReward.query.filter_by(
            relation_bid=relation.relation_bid
        ).one()
        assert relation.relation_status == REFERRAL_RELATION_STATUS_REWARD_SKIPPED_CAP
        assert reward.reward_status == REFERRAL_REWARD_STATUS_SKIPPED_CAP
