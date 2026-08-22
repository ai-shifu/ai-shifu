"""Verify application factory ownership and reuse."""


def test_create_app_reuses_the_owned_application(app: object):
    from app import create_app

    assert create_app() is app
