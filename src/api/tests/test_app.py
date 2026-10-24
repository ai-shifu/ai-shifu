"""Verify application factory ownership and reuse."""


def test_create_app_reuses_the_owned_application(app: object) -> None:
    from app import create_app

    assert create_app() is app
    assert app.extensions["serving_http"] is True


def test_development_factory_requires_explicit_nonproduction_bootstrap(
    monkeypatch: object,
) -> None:
    import app as app_module
    import pytest
    from flask import Flask
    from flaskr.common.config import EnvironmentConfigError
    from flaskr.service.user.verification_codes import get_development_verification_code

    plain_app = Flask(__name__)
    plain_app.config.update(ENV="development", UNIVERSAL_VERIFICATION_CODE="2468")
    monkeypatch.setattr(app_module, "create_app", lambda: plain_app)
    assert get_development_verification_code(plain_app) is None
    assert app_module.create_development_app() is plain_app
    assert get_development_verification_code(plain_app) == "2468"
    plain_app.config["ENV"] = "production"
    assert get_development_verification_code(plain_app) is None
    with pytest.raises(EnvironmentConfigError):
        app_module.create_development_app()
