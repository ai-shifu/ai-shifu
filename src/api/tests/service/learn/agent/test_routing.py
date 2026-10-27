"""Verify that every identified course is taught by 2.0 regardless of the old flag."""

from __future__ import annotations

import pytest
from flaskr.common import config
from flaskr.service.learn.agent import routing


@pytest.mark.parametrize("flag", [None, "", "false", "0", "off", "typo", "true"])
def test_every_identified_course_uses_2_0_whatever_the_old_flag_says(
    monkeypatch: pytest.MonkeyPatch, flag: str | None
) -> None:
    if flag is None:
        monkeypatch.delenv("FLOW_ENGINE_V2_ENABLED", raising=False)
    else:
        monkeypatch.setenv("FLOW_ENGINE_V2_ENABLED", flag)
    for course in ("previously-listed", "never-listed", " newly-created "):
        assert routing.uses_agent_engine(course) is True


@pytest.mark.parametrize("course", ["", "   ", None])
def test_a_missing_course_identifier_is_not_a_course(course: object) -> None:
    assert routing.uses_agent_engine(course) is False


def test_the_old_flag_stays_registered_but_unread() -> None:
    registered = config.ENV_VARS["FLOW_ENGINE_V2_ENABLED"]
    assert "ignored" in registered.description
    assert "FLOW_ENGINE_V2_SHIFU_BIDS" not in config.ENV_VARS
