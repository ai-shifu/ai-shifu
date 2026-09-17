"""Cover which courses the 2.0 engine claims, and what happens when the allowlist is malformed."""

from __future__ import annotations

import pytest
from flaskr.service.learn.agent import routing


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("", frozenset(), id="empty-string"),
        pytest.param(None, frozenset(), id="unset"),
        pytest.param([], frozenset(), id="empty-list"),
        pytest.param("one", frozenset({"one"}), id="single"),
        pytest.param("one,two", frozenset({"one", "two"}), id="comma-separated"),
        pytest.param(" one , two ", frozenset({"one", "two"}), id="padded"),
        pytest.param("one,,two,", frozenset({"one", "two"}), id="blank-entries"),
        pytest.param(["one", " two "], frozenset({"one", "two"}), id="already-a-list"),
        pytest.param("one,one", frozenset({"one"}), id="duplicates"),
        pytest.param(42, frozenset(), id="wrong-type"),
        pytest.param({"one": "x"}, frozenset(), id="mapping-keys-are-not-an-allowlist"),
        pytest.param(("one",), frozenset(), id="tuple-is-not-a-documented-shape"),
    ],
)
def test_the_allowlist_is_read_from_either_shape_the_config_layer_returns(
    raw: object,
    expected: frozenset[str],
) -> None:
    """The value is a list once the config singleton parsed it, a string before that."""
    assert routing._parse_shifu_bids(raw) == expected


def _with_allowlist(monkeypatch: pytest.MonkeyPatch, raw: object) -> None:
    monkeypatch.setattr(routing, "get_config", lambda *_args, **_kwargs: raw)


def test_a_listed_course_is_taught_by_the_agent_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_allowlist(monkeypatch, "shifu-a,shifu-b")
    assert routing.uses_agent_engine("shifu-b") is True


def test_an_unlisted_course_stays_on_the_script_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_allowlist(monkeypatch, "shifu-a")
    assert routing.uses_agent_engine("shifu-b") is False


def test_an_empty_allowlist_keeps_every_course_on_the_script_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production runs with an empty allowlist, so this is the case that must not drift."""
    _with_allowlist(monkeypatch, "")
    assert routing.uses_agent_engine("shifu-a") is False


def test_a_malformed_allowlist_keeps_every_course_on_the_script_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Routing a learner into a runtime nobody chose is worse than ignoring a typo."""
    _with_allowlist(monkeypatch, {"unexpected": "shape"})
    assert routing.uses_agent_engine("shifu-a") is False


def test_a_mapping_does_not_turn_its_own_keys_into_an_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mapping is iterable, so iterating one would admit exactly the course it names."""
    _with_allowlist(monkeypatch, {"shifu-a": "unexpected"})
    assert routing.uses_agent_engine("shifu-a") is False


def test_the_allowlist_never_falls_back_to_shared_database_configuration() -> None:
    """The service-level helper reads sys_configs, which both deployments share.

    Reading it here would let one row route production into 2.0 with its own variable unset, which
    is the failure this module exists to avoid.
    """
    import flaskr.common.config as common_config

    assert routing.get_config is common_config.get_config


@pytest.mark.parametrize(
    "shifu_bid",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="blank"),
        pytest.param(None, id="none"),
    ],
)
def test_a_course_without_an_identifier_never_matches(
    monkeypatch: pytest.MonkeyPatch,
    shifu_bid: object,
) -> None:
    """A blank entry in the allowlist must not become a wildcard."""
    _with_allowlist(monkeypatch, "shifu-a,,")
    assert routing.uses_agent_engine(shifu_bid) is False


def test_the_course_identifier_is_matched_after_trimming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_allowlist(monkeypatch, "shifu-a")
    assert routing.uses_agent_engine("  shifu-a  ") is True


def test_the_allowlist_is_read_through_the_documented_config_key() -> None:
    """Deployments set this name; a rename here silently strands the env they configured."""
    assert routing.V2_SHIFU_BIDS_CONFIG_KEY == "FLOW_ENGINE_V2_SHIFU_BIDS"


def test_the_config_key_is_registered_so_the_environment_reaches_it() -> None:
    """An unregistered key reads as None however carefully a deployment sets it."""
    from flaskr.common.config import ENV_VARS

    registered = ENV_VARS[routing.V2_SHIFU_BIDS_CONFIG_KEY]
    assert registered.type is list
    assert registered.default == []


def test_a_deployment_environment_reaches_the_routing_decision() -> None:
    """Cover the whole path, not just the parser: a typo in the key name passes every other test."""
    from flaskr.common.config import ENV_VARS

    registered = ENV_VARS[routing.V2_SHIFU_BIDS_CONFIG_KEY]
    as_the_config_layer_parses_it = registered.convert_type("shifu-a, shifu-b")

    assert routing._parse_shifu_bids(as_the_config_layer_parses_it) == frozenset(
        {"shifu-a", "shifu-b"}
    )


def test_an_unset_environment_keeps_courses_on_the_script_engine() -> None:
    """Production sets nothing, so the registered default decides what production does."""
    from flaskr.common.config import ENV_VARS

    registered = ENV_VARS[routing.V2_SHIFU_BIDS_CONFIG_KEY]

    assert routing._parse_shifu_bids(registered.convert_type("")) == frozenset()
