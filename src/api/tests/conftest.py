import pytest
from app import create_app


# Path: test/test_flaskr.py
# Compare this snippet from flaskr/plugin/test.py:
# from ..service.schedule import *
#
@pytest.fixture(scope="session", autouse=True)
def app():

    app = create_app()
    from flask_migrate import upgrade

    with app.app_context():
        upgrade("migrations")

    yield app
