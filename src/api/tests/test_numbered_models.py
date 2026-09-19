"""Verify numbered model identity, compatibility fallback, and routing boundaries."""

from types import SimpleNamespace

import pytest
from flaskr.api import llm
from flaskr.api.llm import tiers
from flaskr.service.common.models import AppError

pytestmark = pytest.mark.no_mock_llm


@pytest.fixture(autouse=True)
def model_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Configure sparse numbered slots without contacting providers or storage."""
    config = {
        "LLM_MODEL_1_NAME": "Daily",
        "LLM_MODEL_1_ID": "test/default",
        "LLM_MODEL_3_NAME": "Detailed",
        "LLM_MODEL_3_ID": "test/advanced",
        "LLM_MODEL_7_NAME": "Same route",
        "LLM_MODEL_7_ID": "test/advanced",
    }
    monkeypatch.setattr(
        tiers, "get_config", lambda key, default=None: config.get(key, default)
    )
    monkeypatch.setattr(
        llm, "get_config", lambda key, default=None: config.get(key, default)
    )
    monkeypatch.setattr(llm, "MODEL_SUPPORTED_GENERATION_METHODS", {})
    monkeypatch.setattr(
        llm,
        "get_litellm_params_and_model",
        lambda model: ({"api_key": "test"}, model, "test"),
    )
    monkeypatch.setattr(
        llm,
        "_attach_credit_multipliers",
        lambda _app, options: [
            {**option, "credit_multiplier": 2} for option in options
        ],
    )
    return config


def test_slot_identity_survives_insert_delete_and_restore(
    model_config: dict[str, str],
) -> None:
    """A missing slot falls back temporarily without mutating the original record."""
    record = SimpleNamespace(llm="3")
    assert tiers.course_model_selection(record.llm) == {
        "index": "3",
        "fallback": False,
        "fallback_reason": None,
    }
    model_config["LLM_MODEL_2_NAME"] = "New"
    model_config["LLM_MODEL_2_ID"] = "test/new"
    assert [slot["index"] for slot in tiers.get_configured_model_slots()] == [
        "1",
        "2",
        "3",
        "7",
    ]
    del model_config["LLM_MODEL_3_ID"]
    assert tiers.resolve_course_selection(record.llm)[0] == "test/default"
    assert record.llm == "3"
    model_config["LLM_MODEL_3_ID"] = "test/replacement"
    assert tiers.resolve_course_selection(record.llm)[0] == "test/replacement"


@pytest.mark.parametrize(
    "saved",
    [
        None,
        "",
        "  ",
        "fast",
        "balanced",
        "ultimate",
        "gpt-test",
        "test/advanced",
        "0",
        "10",
        "01",
        3,
    ],
)
def test_legacy_and_invalid_choices_use_default(
    saved: object,
) -> None:
    """Only canonical configured string indices are course selections."""
    resolved, metadata = tiers.resolve_course_selection(saved)
    assert resolved == "test/default"
    assert metadata["model_index"] == "1"
    assert metadata["model_selection_original"] == saved
    assert metadata["model_selection_fallback"] is True
    assert tiers.normalize_course_model(saved) == "1"


def test_incomplete_slots_are_not_selectable(model_config: dict[str, str]) -> None:
    """Optional pairs need both a nonblank display name and a model binding."""
    model_config.update(
        LLM_MODEL_2_NAME="Name only",
        LLM_MODEL_4_ID="test/model-only",
        LLM_MODEL_5_NAME="   ",
        LLM_MODEL_5_ID="test/blank-name",
    )
    assert [slot["index"] for slot in tiers.get_configured_model_slots()] == [
        "1",
        "3",
        "7",
    ]
    for index in ("2", "4", "5", "9"):
        assert tiers.course_model_selection(index) == {
            "index": "1",
            "fallback": True,
            "fallback_reason": "unconfigured_index",
        }


def test_missing_default_binding_errors(model_config: dict[str, str]) -> None:
    """Fallback cannot invent a physical model when slot one is unavailable."""
    del model_config["LLM_MODEL_1_ID"]
    with pytest.raises(AppError):
        tiers.resolve_course_selection("legacy-model")


def test_provider_route_failure_does_not_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete slot whose route is unusable must fail instead of changing model."""
    requested = []

    def missing_route(model: str) -> tuple:
        requested.append(model)
        return None, model, None

    monkeypatch.setattr(llm, "get_litellm_params_and_model", missing_route)
    with pytest.raises(AppError):
        tiers.resolve_course_selection("3")
    assert requested == ["test/advanced"]


def test_course_snapshot_is_idempotent_and_keeps_revision(
    model_config: dict[str, str],
) -> None:
    """Configuration changes cannot alter the model of an already resolved call."""
    record = SimpleNamespace(llm="old/model", id=23, __tablename__="published_shifu")
    model, metadata = tiers.resolve_course_selection(
        record.llm, tiers.selection_metadata(record)
    )
    model_config["LLM_MODEL_1_ID"] = "test/changed"
    assert tiers.resolve_selection(model, metadata) == (model, metadata)
    assert metadata["model_selection_record_id"] == 23
    assert metadata["model_selection_table"] == "published_shifu"
    assert metadata["model_selection_original"] == "old/model"
    assert record.llm == "old/model"


def test_generic_physical_models_and_live_are_not_course_normalized() -> None:
    """Course fallback cannot replace gateway, internal, or Live model identifiers."""
    assert (
        tiers.resolve_selection("unconfigured/physical")[0] == "unconfigured/physical"
    )
    record = SimpleNamespace(ask_llm="gemini-3.8-live")
    metadata = tiers.selection_metadata(record, follow_up=True)
    assert metadata["model_selection_scope"] == "live"
    assert tiers.resolve_selection(record.ask_llm, metadata)[0] == record.ask_llm
    assert "model_index" not in metadata


def test_course_and_physical_catalogs_share_slots_without_leaking_ids() -> None:
    """Course slots remain distinct while the physical catalog deduplicates bindings."""
    options = llm.get_model_tier_options(object())
    assert [option["index"] for option in options] == ["1", "3", "7"]
    assert [option["is_default"] for option in options] == [True, False, False]
    assert all(option["available"] for option in options)
    assert all("model" not in option for option in options)
    assert "test/" not in str(options)
    assert [option["model"] for option in llm.get_course_models(object())] == [
        "1",
        "3",
        "7",
    ]
    assert llm.get_current_models(object()) == [
        {"model": "test/default", "display_name": "Daily", "credit_multiplier": 2},
        {"model": "test/advanced", "display_name": "Detailed", "credit_multiplier": 2},
    ]


def test_old_allowlist_and_discovered_models_never_define_catalog(
    monkeypatch: pytest.MonkeyPatch, model_config: dict[str, str]
) -> None:
    """Only numbered bindings can add selectable or gateway catalog entries."""
    model_config.clear()
    model_config.update(
        LLM_ALLOWED_MODELS="test/old",
        LLM_ALLOWED_MODEL_DISPLAY_NAMES="Old",
        **{"llm-allowed-models": "test/legacy"},
    )
    monkeypatch.setattr(
        llm,
        "PROVIDER_STATES",
        {
            "test": llm.ProviderState(
                enabled=True, params={"api_key": "test"}, models=["test/discovered"]
            )
        },
    )
    assert llm.get_current_models(object()) == []
    assert llm.get_model_tier_options(object()) == []


def test_reusing_metadata_with_a_new_selection_resolves_the_new_slot() -> None:
    """Only an unchanged physical snapshot can bypass selection resolution."""
    _, previous = tiers.resolve_course_selection("old/model")
    resolved, metadata = tiers.resolve_course_selection("3", previous)
    assert resolved == "test/advanced"
    assert metadata["model_selection_original"] == "3"
    assert metadata["model_index"] == "3"
    assert metadata["model_selection_fallback"] is False
    assert metadata["resolved_model"] == resolved


@pytest.mark.parametrize("configured_model", ["gemini-3.8-live", "test/bidi", "3"])
def test_configured_nontext_bindings_fail_without_default_switch(
    monkeypatch: pytest.MonkeyPatch, model_config: dict[str, str], configured_model: str
) -> None:
    """A configured slot remains itself even when its binding is unsuitable."""
    model_config["LLM_MODEL_3_ID"] = configured_model
    monkeypatch.setattr(
        llm,
        "MODEL_SUPPORTED_GENERATION_METHODS",
        {"test/bidi": frozenset({"bidiGenerateContent"})},
    )
    with pytest.raises(AppError):
        tiers.resolve_course_selection("3")
    option = next(
        item for item in llm.get_model_tier_options(object()) if item["index"] == "3"
    )
    assert option["available"] is False


def test_numbered_environment_config_never_probes_persisted_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent optional slots must not make SQL or Redis configuration requests."""

    def unexpected_lookup(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Persisted config must not be consulted for numbered slots")

    monkeypatch.setattr(tiers, "get_override_config", unexpected_lookup)
    assert [slot["index"] for slot in tiers.get_configured_model_slots()] == [
        "1",
        "3",
        "7",
    ]


def test_process_local_slot_overrides_support_isolated_arena_runs() -> None:
    """Arena's explicit thread-local overrides do not require persisted config."""
    from flaskr.service.config import config_overrides

    with config_overrides(
        {"LLM_MODEL_1_NAME": "Arena", "LLM_MODEL_1_ID": "test/arena"}
    ):
        assert tiers.resolve_course_selection("legacy")[0] == "test/arena"
    assert tiers.resolve_course_selection("legacy")[0] == "test/default"
