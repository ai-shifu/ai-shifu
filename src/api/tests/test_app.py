import pytest


@pytest.fixture
def test_client(app):
    print("test_client")
