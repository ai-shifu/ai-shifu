import os
import pytest


@pytest.fixture(scope="session")
def app():
    os.environ.setdefault("REDIS_MOCK", "true")
    os.environ.setdefault("LOGGING_PATH", "/tmp/test.log")
    os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    from app import create_app

    app = create_app()
    yield app


@pytest.fixture
def test_client(app):
    with app.test_client() as client:
        yield client


@pytest.fixture
def token():
    return ""
