import pytest
from app import create_app
# Path: test/test_flaskr.py
# Compare this snippet from flaskr/plugin/test.py:
# from ..service.schedule import *
# 

# print("test_flaskr.py")
# @pytest.fixture(scope="session", autouse=True)
# def app():
#     app = create_app('test_sifu')
#     yield app


@pytest.fixture
def test_client(app):
    print ("test_client")