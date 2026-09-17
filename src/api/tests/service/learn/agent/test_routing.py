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
