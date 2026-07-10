from unittest.mock import Mock

import pytest
import requests

from flaskr.service.shifu import funcs


def test_download_image_from_url_retries_transient_timeouts(monkeypatch):
    calls = []
    expected_response = Mock()
    expected_response.raise_for_status.return_value = None

    def fake_get(url, headers, timeout):
        calls.append((url, headers, timeout))
        if len(calls) < 3:
            raise requests.Timeout("upstream timed out")
        return expected_response

    monkeypatch.setattr(funcs.requests, "get", fake_get)

    response = funcs._download_image_from_url("https://example.com/image.jpg", {"Accept": "image/*"})

    assert response is expected_response
    assert [call[2] for call in calls] == [10, 20, 30]


def test_download_image_from_url_does_not_retry_http_errors(monkeypatch):
    calls = []
    expected_response = Mock()
    expected_response.raise_for_status.side_effect = requests.HTTPError("404")

    def fake_get(url, headers, timeout):
        calls.append(timeout)
        return expected_response

    monkeypatch.setattr(funcs.requests, "get", fake_get)

    with pytest.raises(requests.HTTPError):
        funcs._download_image_from_url("https://example.com/missing.jpg", {})

    assert calls == [10]
