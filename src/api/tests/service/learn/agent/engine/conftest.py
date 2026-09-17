"""Async support for the engine's own tests.

The engine is asyncio throughout, and this repository has no pytest-asyncio. anyio ships a pytest
plugin and is already a dependency, so these tests run on it: `anyio_backend` pins the one backend
the engine targets, and each module with async tests carries `pytestmark = pytest.mark.anyio`.
"""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
