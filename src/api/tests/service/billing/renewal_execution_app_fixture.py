from __future__ import annotations

from collections.abc import Generator

import flaskr.dao as dao
import pytest
from flask import Flask
from tests.common.fixtures.bill_products import build_bill_products


@pytest.fixture
def billing_renewal_app() -> Generator[Flask, None, None]:
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
        dao.db.session.add_all(build_bill_products())
        dao.db.session.commit()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()
