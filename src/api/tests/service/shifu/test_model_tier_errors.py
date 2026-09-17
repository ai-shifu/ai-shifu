"""Keep tier configuration errors distinct from unexpected resolver failures."""

import pytest
from flaskr.api import llm
from flaskr.api.llm import tiers
from flaskr.service.common.models import ERROR_CODE, AppError


@pytest.mark.parametrize(
    "error",
    [RuntimeError("resolver failed"), AppError("storage failed", 9999)],
)
@pytest.mark.parametrize("failure_site", ["configuration", "provider", "resolver"])
def test_tier_options_propagate_unexpected_failures(
    app: object, monkeypatch: pytest.MonkeyPatch, error: Exception, failure_site: str
) -> None:
    """Only missing tier/provider configuration becomes ordinary unavailability."""
    monkeypatch.setattr(tiers, "get_config", lambda *_args: "configured-model")

    def fail(*_args: object) -> None:
        raise error

    if failure_site == "configuration":
        monkeypatch.setattr(tiers, "get_config", fail)
    elif failure_site == "provider":
        monkeypatch.setattr(llm, "get_litellm_params_and_model", fail)
    else:
        monkeypatch.setattr(tiers, "resolve_tier_model", fail)
    with app.app_context(), pytest.raises(type(error)) as captured:
        llm.get_model_tier_options(app)
    assert captured.value is error


def test_tier_options_hide_expected_provider_configuration_errors(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tiers, "get_config", lambda *_args: "private-model")

    def missing_provider(*_args: object) -> None:
        message = "private-model provider not configured"
        raise AppError(
            message,
            ERROR_CODE["server.llm.specifiedLlmNotConfigured"],
        )

    monkeypatch.setattr(llm, "get_litellm_params_and_model", missing_provider)
    with app.app_context():
        options = llm.get_model_tier_options(app)
    assert len(options) == 3
    assert all(item["available"] is False for item in options)
    assert "private-model" not in str(options)
