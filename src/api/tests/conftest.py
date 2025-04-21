import pytest
from app import create_app

# Path: test/test_flaskr.py
# Compare this snippet from flaskr/plugin/test.py:
# from ..service.schedule import *
#

print("test_flaskr.py")


@pytest.fixture(scope="session", autouse=True)
def app():
    print("test app init")
    app = create_app()
    yield app
    print("test app close")


@pytest.fixture
def test_client(app):
    with app.test_client() as client:
        yield client
