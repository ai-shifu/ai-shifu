"""Verify the post_fork Langfuse reset sequence rebuilds fresh SDK state.

The gunicorn post_fork hook clears the LangfuseResourceManager singleton
registry and resets the global OpenTelemetry tracer provider so each worker
builds its own exporter state instead of reusing connections inherited from
the preloaded master. These tests exercise that reset sequence directly:
after the reset, constructing a client again must produce a NEW resource
manager (not the cached one) and a NEW tracer provider.
"""

import pytest

pytest.importorskip("langfuse")
pytest.importorskip("opentelemetry")

from langfuse import Langfuse  # noqa: E402
from langfuse._client.resource_manager import LangfuseResourceManager  # noqa: E402
from opentelemetry import trace as otel_trace_api  # noqa: E402
from opentelemetry.util._once import Once  # noqa: E402


def _reset_langfuse_after_fork():
    # Mirrors the sequence in src/api/gunicorn.conf.py post_fork. Kept in
    # sync manually; the assertions below are what the hook relies on.
    LangfuseResourceManager._instances.clear()
    otel_trace_api._TRACER_PROVIDER = None
    otel_trace_api._TRACER_PROVIDER_SET_ONCE = Once()


@pytest.fixture(autouse=True)
def _clean_singletons():
    _reset_langfuse_after_fork()
    yield
    _reset_langfuse_after_fork()


def _make_client() -> Langfuse:
    # tracing_enabled default triggers resource-manager creation; no network
    # traffic happens until a flush, which these tests never perform.
    return Langfuse(
        public_key="pk-test-post-fork",
        secret_key="sk-test-post-fork",
        host="http://localhost:9",
    )


def test_reset_clears_singleton_registry_and_rebuilds_resources():
    client = _make_client()
    first_resources = client._resources
    assert LangfuseResourceManager._instances

    # Without a reset the SDK returns the cached (fork-inherited) manager.
    cached = _make_client()
    assert cached._resources is first_resources

    _reset_langfuse_after_fork()
    assert not LangfuseResourceManager._instances

    rebuilt = _make_client()
    assert rebuilt._resources is not first_resources


def test_reset_allows_registering_a_fresh_tracer_provider():
    _make_client()
    first_provider = otel_trace_api.get_tracer_provider()
    assert not isinstance(first_provider, otel_trace_api.ProxyTracerProvider)

    _reset_langfuse_after_fork()

    # After the reset the global returns to the proxy state, so the next
    # client registers a brand-new provider instead of attaching another
    # span processor to the master's provider.
    assert isinstance(
        otel_trace_api.get_tracer_provider(), otel_trace_api.ProxyTracerProvider
    )
    _make_client()
    second_provider = otel_trace_api.get_tracer_provider()
    assert not isinstance(second_provider, otel_trace_api.ProxyTracerProvider)
    assert second_provider is not first_provider
