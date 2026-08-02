import re
import types
import unittest
from unittest.mock import patch

from flask import Flask

from flaskr.api.langfuse import (
    MockClient,
    coerce_langfuse_trace_id,
    get_request_trace_id,
    resolve_langfuse_trace_id,
)
from flaskr.common.log import thread_local

TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class CoerceTraceIdTests(unittest.TestCase):
    def test_passes_through_valid_w3c_trace_id(self):
        valid = "0123456789abcdef0123456789abcdef"
        self.assertEqual(coerce_langfuse_trace_id(valid), valid)

    def test_maps_arbitrary_ids_deterministically(self):
        first = coerce_langfuse_trace_id("my-request-id")
        second = coerce_langfuse_trace_id("my-request-id")
        self.assertEqual(first, second)
        self.assertRegex(first, TRACE_ID_RE)
        self.assertNotEqual(first, coerce_langfuse_trace_id("other-request-id"))

    def test_generates_random_id_when_seed_missing(self):
        generated = coerce_langfuse_trace_id(None)
        self.assertRegex(generated, TRACE_ID_RE)


class RequestTraceIdTests(unittest.TestCase):
    def tearDown(self):
        for attr in ("request_id",):
            if hasattr(thread_local, attr):
                delattr(thread_local, attr)

    def test_prefers_thread_local_request_id(self):
        app = Flask("langfuse-thread-local")
        thread_local.request_id = "thread-local-request-id"

        with app.test_request_context(headers={"X-Request-ID": "header-request-id"}):
            self.assertEqual(
                get_request_trace_id(),
                coerce_langfuse_trace_id("thread-local-request-id"),
            )

    def test_falls_back_to_request_header(self):
        if hasattr(thread_local, "request_id"):
            delattr(thread_local, "request_id")
        fake_request = types.SimpleNamespace(
            headers={"X-Request-ID": "header-request-id"}
        )
        original_request = get_request_trace_id.__globals__["request"]
        get_request_trace_id.__globals__["request"] = fake_request
        try:
            self.assertEqual(
                get_request_trace_id(),
                coerce_langfuse_trace_id("header-request-id"),
            )
        finally:
            get_request_trace_id.__globals__["request"] = original_request

    def test_uses_generated_uuid_when_request_id_is_missing(self):
        fake_uuid = types.SimpleNamespace(hex="0123456789abcdef0123456789abcdef")

        with patch("flaskr.api.langfuse.uuid.uuid4", return_value=fake_uuid):
            self.assertEqual(get_request_trace_id(), fake_uuid.hex)


class ResolveLangfuseTraceIdTests(unittest.TestCase):
    def tearDown(self):
        for attr in ("request_id",):
            if hasattr(thread_local, attr):
                delattr(thread_local, attr)

    def test_prefers_explicit_string_trace_id(self):
        observation = types.SimpleNamespace(trace_id="observation-trace-id")
        self.assertEqual(
            resolve_langfuse_trace_id(observation, "explicit-trace-id"),
            "explicit-trace-id",
        )

    def test_falls_back_to_observation_string_trace_id(self):
        observation = types.SimpleNamespace(trace_id="observation-trace-id")
        self.assertEqual(resolve_langfuse_trace_id(observation), "observation-trace-id")

    def test_ignores_non_string_trace_id_from_mock_client(self):
        # When Langfuse is disabled, observations are MockClient instances whose
        # __getattr__ returns a bound method for any attribute, including
        # ``trace_id``. That object must never be used as the trace id.
        thread_local.request_id = "request-trace-id"

        self.assertEqual(
            resolve_langfuse_trace_id(MockClient()),
            coerce_langfuse_trace_id("request-trace-id"),
        )

    def test_ignores_empty_string_trace_ids(self):
        thread_local.request_id = "request-trace-id"
        observation = types.SimpleNamespace(trace_id="")

        self.assertEqual(
            resolve_langfuse_trace_id(observation, ""),
            coerce_langfuse_trace_id("request-trace-id"),
        )
