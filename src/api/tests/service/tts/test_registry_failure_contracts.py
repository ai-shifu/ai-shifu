"""Protect TTS discovery, localization and unavailable pricing fallbacks."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.api import tts
from flaskr.service.billing import charges


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> dict:
    values = {}
    monkeypatch.setattr(
        tts, "get_config", lambda key, default=None: values.get(key, default)
    )
    monkeypatch.setattr(tts, "_provider_instances", {})
    return values


def test_provider_cache_normalizes_names_and_rejects_unknown_without_caching(
    settings: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = Mock()
    factory = Mock(return_value=provider)
    monkeypatch.setattr(tts, "_PROVIDER_REGISTRY", {"provider": factory})
    assert tts.get_tts_provider(" Provider ") is provider
    assert tts.get_tts_provider("provider") is provider
    factory.assert_called_once()
    with pytest.raises(ValueError, match="Unknown TTS provider: unknown"):
        tts.get_tts_provider("unknown")
    assert "unknown" not in tts._provider_instances
    assert not tts.is_tts_configured("unknown")
    settings["MINIMAX_API_KEY"] = "configured"
    assert tts._resolve_provider_name("default") == "minimax"


def test_discovery_keeps_usable_provider_when_other_config_export_fails(
    settings: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = Mock(side_effect=RuntimeError("provider unavailable"))
    good = Mock()
    good.return_value.get_provider_config.return_value.to_dict.return_value = {
        "name": "usable",
        "models": [],
    }
    monkeypatch.setattr(
        tts,
        "_iter_provider_classes",
        lambda **_kwargs: iter([("broken", broken), ("usable", good)]),
    )
    monkeypatch.setattr(tts, "_resolve_credit_multiplier_label", lambda *_args: None)
    result = tts.get_all_provider_configs()
    assert [provider["name"] for provider in result["providers"]] == ["usable"]
    assert result["model_options"][0]["value"] == "usable/default"
    settings["TTS_DEFAULT_MODEL"] = "missing/default"
    assert not tts.get_all_provider_configs()["model_options"][0]["is_default"]


@pytest.mark.parametrize("raw", ["{bad", "[]", '"text"', 42])
def test_malformed_display_name_registry_is_ignored(
    settings: dict, raw: object
) -> None:
    settings["TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON"] = raw
    assert tts._parse_tts_display_names() == {}


def test_display_name_registry_ignores_unqualified_keys_and_normalizes_provider(
    settings: dict,
) -> None:
    settings["TTS_ALLOWED_MODEL_DISPLAY_NAMES_JSON"] = {
        "bad": "ignored",
        " Provider/model ": "Display",
    }
    assert tts._parse_tts_display_names() == {"provider/model": "Display"}


def test_allowlist_skips_invalid_entries_and_deduplicates_normalized_keys(
    settings: dict,
) -> None:
    settings["TTS_ALLOWED_MODELS"] = [
        None,
        "",
        "bad",
        "Provider/model",
        " provider/model ",
    ]
    assert tts._parse_allowed_tts_model_keys() == ["provider/model"]
    settings["TTS_DEFAULT_MODEL"] = "bad"
    assert tts._parse_default_tts_model_key() == ""


def test_localized_labels_follow_request_precedence_then_language_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tts, "get_current_language", lambda: "en-US")
    labels = {
        "voice/default": {"fr-FR": "French", "zh-CN": "Chinese", "en-US": "English"}
    }
    app = Flask(__name__)
    with app.test_request_context(
        "/?language=fr-CA", headers={"X-Language": "zh-CN", "Accept-Language": "en-US"}
    ):
        assert (
            tts._resolve_localized_tts_label(labels, "voice/default", "Fallback")
            == "French"
        )
    with app.test_request_context(
        "/", headers={"X-Locale": "zh_CN", "Accept-Language": "fr-FR;q=0.8,en-US"}
    ):
        assert (
            tts._resolve_localized_tts_label(labels, "voice/default", "Fallback")
            == "Chinese"
        )
    assert tts._resolve_locale_entry(labels["voice/default"], "") == ""
    assert (
        tts._resolve_localized_tts_label(
            {"voice/default": " Fixed "}, "voice/default", "Fallback"
        )
        == "Fixed"
    )


@pytest.mark.parametrize("stage", ["baseline", "chars", "rate", "exception"])
def test_incomplete_pricing_hides_multiplier_without_breaking_provider_config(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    monkeypatch.setattr(
        tts,
        "load_llm_credit_1x_unit_cost",
        Mock(return_value=None if stage == "baseline" else Decimal(1)),
    )
    monkeypatch.setattr(
        tts,
        "_load_tts_chars_per_llm_token",
        Mock(return_value=0 if stage == "chars" else Decimal(1)),
    )
    rate = Mock(return_value=None if stage == "rate" else Decimal(1))
    if stage == "exception":
        rate.side_effect = RuntimeError("database unavailable")
    monkeypatch.setattr(tts, "_load_usage_rate_unit_cost", rate)
    assert tts._resolve_credit_multiplier_label("provider", "model") is None


@pytest.mark.parametrize("raw", [None, "", "broken", "-1", "0"])
def test_missing_or_invalid_character_ratio_cannot_create_a_multiplier(
    settings: dict, raw: object
) -> None:
    settings["TTS_CHARS_PER_LLM_TOKEN"] = raw
    assert tts._load_tts_chars_per_llm_token() is None


def test_rate_lookup_continues_past_missing_wildcard_and_malformed_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load = Mock(
        side_effect=[
            None,
            SimpleNamespace(provider="*", model="*", unit_size=1, credits_per_unit=1),
            SimpleNamespace(
                provider="provider", model="bad", unit_size="broken", credits_per_unit=1
            ),
            SimpleNamespace(
                provider="provider", model="good", unit_size=10, credits_per_unit="0.5"
            ),
        ]
    )
    monkeypatch.setattr(charges, "load_usage_rate", load)
    assert tts._load_usage_rate_unit_cost(
        usage_type=1,
        provider="provider",
        model_candidates=["missing", "wildcard", "bad", "good"],
        billing_metric=2,
        ignore_global_wildcard=True,
    ) == Decimal("0.05")
    calls = load.call_args_list
    assert [call.kwargs["usage"].model for call in calls] == [
        "missing",
        "wildcard",
        "bad",
        "good",
    ]
    assert len({call.kwargs["settlement_at"] for call in calls}) == 1
    load.side_effect = None
    load.return_value = None
    assert (
        tts._load_usage_rate_unit_cost(
            usage_type=1, provider="provider", model_candidates=[], billing_metric=2
        )
        is None
    )
    assert load.call_args.kwargs["usage"].model == ""


def test_model_option_generation_ignores_malformed_model_items(
    settings: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tts, "_resolve_credit_multiplier_label", lambda *_args: "2x")
    options = tts._build_tts_model_options(
        [
            (
                "provider",
                {"label": "Provider", "models": [None, "bad", {}, {"value": "model"}]},
            )
        ]
    )
    assert options == [
        {
            "value": "provider/model",
            "label": "Provider / model",
            "provider": "provider",
            "model": "model",
            "credit_multiplier_label": "2x",
            "is_default": False,
        }
    ]
    settings["TTS_ALLOWED_MODELS"] = "unknown/model"
    assert tts._build_tts_model_options([("provider", {})]) == []
