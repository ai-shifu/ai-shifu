"""Verify billing value object JSON response serialization."""

from flaskr.route.common import make_common_response
from flaskr.service.billing.value_objects import JsonObjectMap


def test_json_object_map_serializes_in_common_response() -> None:
    response = make_common_response(
        {
            "metadata": JsonObjectMap(
                values={
                    "source": "provider-prices",
                    "nested": JsonObjectMap(values={"key": "value"}),
                }
            )
        }
    )

    payload = response.get_json()

    assert payload["code"] == 0
    assert payload["data"]["metadata"] == {
        "source": "provider-prices",
        "nested": {"key": "value"},
    }
