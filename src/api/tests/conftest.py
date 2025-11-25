import os
import pytest

# Prevent accidental loading of user/global .env files during tests
os.environ.setdefault("SKIP_LOAD_DOTENV", "1")
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")

from app import create_app
from flask_migrate import upgrade


# Path: test/test_flaskr.py
# Compare this snippet from flaskr/plugin/test.py:
# from ..service.schedule import *
#
@pytest.fixture(scope="session", autouse=True)
def app():
    if os.getenv("SKIP_APP_FIXTURE"):
        yield None
        return
    app = create_app()

    with app.app_context():
        # Allow skipping DB migrations in CI/unit-only runs
        if not os.getenv("SKIP_DB_MIGRATIONS_FOR_TESTS"):
            upgrade("migrations")

    yield app


@pytest.fixture
def test_client(app):
    with app.test_client() as client:
        yield client


@pytest.fixture
def token():
    return ""
