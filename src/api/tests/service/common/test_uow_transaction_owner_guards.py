"""Every flow whose correctness depends on owning the outermost transaction.

These functions commit in several steps (claim -> external call -> finalize),
or rely on an ``IntegrityError`` reaching their own handler. Nested inside a
caller's unit of work neither contract holds: the intermediate commits never
happen, and the conflict surfaces at the caller's commit instead. The guard
turns that into a loud failure; this module pins the list of guarded flows so
a future migration cannot quietly drop one.

The inventory is checked by reading the source rather than by calling the
functions: importing those service modules from here would change the import
order of the whole suite, and several test modules install stubs based on what
is already imported.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from flaskr.dao import uow
from flaskr.dao.uow import unit_of_work

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[3] / "flaskr"

_GUARDED = (
    ("service/learn/lesson_feedback.py", "submit_lesson_feedback"),
    ("service/billing/wallets.py", "grant_manual_credit_wallet_balance"),
    (
        "service/billing/referral_reward_grants.py",
        "grant_referral_reward_credits_to_user",
    ),
    ("service/referral/service.py", "process_referral_post_auth"),
    ("service/referral/service.py", "retry_pending_referral_rewards"),
    ("service/billing/notifications.py", "deliver_billing_paid_feishu"),
    ("service/billing/notifications.py", "deliver_subscription_purchase_sms"),
    ("service/billing/checkout.py", "create_billing_order_checkout"),
    ("service/billing/checkout.py", "sync_billing_order"),
    ("service/billing/trials.py", "_bootstrap_new_creator_trial_credits"),
    ("service/billing/trials.py", "_backfill_missing_creator_trial_credits"),
    ("service/user/utils.py", "_prepare_verification_challenge"),
    ("service/user/onboarding.py", "complete_onboarding_scene"),
    ("service/tts/minimax_voice_clone.py", "submit_minimax_voice_clone"),
    ("service/tts/minimax_voice_clone.py", "run_minimax_voice_clone"),
    ("service/tts/minimax_voice_clone.py", "retry_minimax_voice_clone"),
)


def _guard_calls(path: str, function_name: str) -> list[ast.Call]:
    tree = ast.parse((_BACKEND_ROOT / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return [
                call
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and getattr(call.func, "id", getattr(call.func, "attr", ""))
                == "require_transaction_owner"
            ]
    message = f"{function_name} not found in {path}"
    raise AssertionError(message)


@pytest.mark.parametrize(("path", "function_name"), _GUARDED)
def test_guarded_entry_point_declares_the_guard(path: str, function_name: str) -> None:
    calls = _guard_calls(path, function_name)
    assert len(calls) == 1, f"{function_name} must call require_transaction_owner once"
    # The app has to be passed, otherwise a foreign-app caller is rejected.
    assert len(calls[0].args) == 2, (
        f"{function_name} must pass its app to require_transaction_owner"
    )


def test_the_guard_rejects_a_nested_caller_of_the_same_app(app: object) -> None:
    with app.app_context(), unit_of_work():
        with pytest.raises(RuntimeError, match="must not be called"):
            uow.require_transaction_owner("probe", app)
        # Without the app argument the guard cannot tell apps apart and stays
        # strict.
        with pytest.raises(RuntimeError, match="must not be called"):
            uow.require_transaction_owner("probe")


def test_the_guard_allows_a_unit_of_work_of_another_app(app: object) -> None:
    """`app_context_scope` hands a foreign-app call a fresh session and depth.

    Rejecting it would break the celery task app and the multi-app fixtures.
    The foreign app is never entered here: what matters is the decision the
    guard makes about it while another app's unit of work is active.
    """
    from flask import Flask

    other = Flask("guard-other-app")
    with app.app_context(), unit_of_work():
        uow.require_transaction_owner("probe", other)


def test_the_guard_is_a_noop_outside_a_unit_of_work(app: object) -> None:
    with app.app_context():
        uow.require_transaction_owner("probe", app)
        uow.require_transaction_owner("probe")
