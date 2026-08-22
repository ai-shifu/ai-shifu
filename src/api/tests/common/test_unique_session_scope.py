"""Unique scoped-session scope tokens across app contexts.

The stock Flask-SQLAlchemy scope function keys sessions on id(app_ctx) - a
recycled memory address. These tests pin the replacement's contract: a
stable token within one context, a NEW token for every context (so a later
context can never adopt a dead context's registry slot), and normal session
lifecycle via teardown.
"""

import pytest
from flaskr.dao import _unique_app_ctx_scope, db


def test_scope_token_is_stable_within_a_context(app: object):
    with app.app_context():
        first = _unique_app_ctx_scope()
        second = _unique_app_ctx_scope()
        assert first == second


def test_scope_token_never_repeats_across_contexts(app: object):
    tokens = []
    for _ in range(50):
        with app.app_context():
            tokens.append(_unique_app_ctx_scope())
    # id(app_ctx) would collide across this loop (the context object is
    # freed each iteration and the allocator reuses the address); the token
    # must not.
    assert len(set(tokens)) == len(tokens)


def test_nested_contexts_get_distinct_tokens(app: object):
    with app.app_context():
        outer = _unique_app_ctx_scope()
        with app.app_context():
            inner = _unique_app_ctx_scope()
            assert inner != outer
        assert _unique_app_ctx_scope() == outer


def test_sessions_are_isolated_per_context_and_removed_on_teardown(app: object):
    with app.app_context():
        outer_token = _unique_app_ctx_scope()
        outer_session = db.session()
        with app.app_context():
            inner_token = _unique_app_ctx_scope()
            inner_session = db.session()
            assert inner_session is not outer_session
        # Back in the outer context the registry must still resolve to the
        # outer session (the nested teardown removed only its own slot).
        assert db.session() is outer_session

    # Both slots created by this test must be cleaned up by teardown - a
    # lingering slot would be exactly the leaked-session condition the
    # unique tokens defend against.
    registry_map = db.session.registry.registry
    assert outer_token not in registry_map
    assert inner_token not in registry_map


def test_scope_raises_outside_app_context():
    with pytest.raises(RuntimeError):
        _unique_app_ctx_scope()
