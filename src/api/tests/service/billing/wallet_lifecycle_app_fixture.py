"""Provide wallet lifecycle app fixture support for service billing tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr import dao

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def billing_wallet_lifecycle_app() -> Generator[Flask, None, None]:
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()
