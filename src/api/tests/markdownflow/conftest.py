"""Run the library's asynchronous tests on its supported event loop."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
