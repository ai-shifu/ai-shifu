"""Every flow whose correctness depends on owning the outermost transaction.

These functions commit in several steps (claim -> external call -> finalize),
or rely on an ``IntegrityError`` reaching their own handler. Nested inside a
caller's unit of work neither contract holds: the intermediate commits never
happen, and the conflict surfaces at the caller's commit instead. The guard
turns that into a loud failure; this module pins the list of guarded flows so
a future migration cannot quietly drop one.
"""

from __future__ import annotations

import inspect
from importlib import import_module

import pytest
from flaskr.dao.uow import unit_of_work

_GUARDED = (
    ("flaskr.service.learn.lesson_feedback", "submit_lesson_feedback"),
    ("flaskr.service.billing.wallets", "grant_manual_credit_wallet_balance"),
    (
        "flaskr.service.billing.referral_reward_grants",
        "grant_referral_reward_credits_to_user",
    ),
    ("flaskr.service.referral.service", "process_referral_post_auth"),
    ("flaskr.service.billing.notifications", "deliver_billing_paid_feishu"),
    ("flaskr.service.billing.notifications", "deliver_subscription_purchase_sms"),
    ("flaskr.service.billing.checkout", "create_billing_order_checkout"),
    ("flaskr.service.billing.checkout", "sync_billing_order"),
    ("flaskr.service.billing.trials", "_bootstrap_new_creator_trial_credits"),
    ("flaskr.service.billing.trials", "_backfill_missing_creator_trial_credits"),
    ("flaskr.service.referral.service", "retry_pending_referral_rewards"),
    ("flaskr.service.user.utils", "_prepare_verification_challenge"),
    ("flaskr.service.user.onboarding", "complete_onboarding_scene"),
    ("flaskr.service.tts.minimax_voice_clone", "submit_minimax_voice_clone"),
    ("flaskr.service.tts.minimax_voice_clone", "run_minimax_voice_clone"),
    ("flaskr.service.tts.minimax_voice_clone", "retry_minimax_voice_clone"),
)


def _placeholder_call(func: object, app: object) -> None:
    """Call ``func`` with placeholder arguments.

    The guard is the first statement in every guarded body, so it runs before
    any validation and the placeholder values never reach real logic.
    """
    args = []
    kwargs = {}
    for name, parameter in inspect.signature(func).parameters.items():
        if parameter.default is not inspect.Parameter.empty:
            continue
        value = app if name == "app" else ""
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            kwargs[name] = value
        else:
            args.append(value)
    func(*args, **kwargs)


@pytest.mark.parametrize(("module_name", "attr"), _GUARDED)
def test_guarded_entry_point_rejects_a_nested_caller(
    app: object, module_name: str, attr: str
) -> None:
    func = getattr(import_module(module_name), attr)

    def call_nested() -> None:
        with unit_of_work():
            _placeholder_call(func, app)

    with app.app_context(), pytest.raises(RuntimeError, match="must not be called"):
        call_nested()


def test_a_unit_of_work_of_another_app_is_not_a_nesting_violation(
    app: object,
) -> None:
    """`app_context_scope` hands a foreign-app call a fresh session and depth.

    Rejecting it would break the celery task app and the multi-app fixtures,
    so the guard only fires when the caller's own context would be reused.
    The foreign app is never entered here: what matters is the decision the
    guard makes about it while another app's unit of work is active.
    """
    from flask import Flask
    from flaskr.dao import uow

    other = Flask("guard-other-app")

    with app.app_context(), unit_of_work():
        # The active unit of work belongs to this app: a real violation.
        with pytest.raises(RuntimeError, match="must not be called"):
            uow.require_transaction_owner("probe", app)
        # A different app: app_context_scope will reset the depth for it.
        uow.require_transaction_owner("probe", other)
        # Without the app argument the guard cannot tell them apart and
        # stays strict.
        with pytest.raises(RuntimeError, match="must not be called"):
            uow.require_transaction_owner("probe")
