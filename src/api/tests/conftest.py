import pytest
from flaskr import create_app
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