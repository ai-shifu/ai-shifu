"""Keep Skill version-header validation bounded and backward compatible."""

import pytest
from flask import Flask
from flaskr.service.common import skill_request_analytics as analytics


@pytest.mark.parametrize(
    "version",
    [
        "0.0.0",
        "2.7.1",
        "001.02.003",
        "2.7.1-rc.1",
        "2.7.1+build.2",
        "2.7.1-rc.1+build.2",
        "2.7.1-a-b+c-d",
        "2.7.1-AZaz09.-+AZaz09.-",
        # These suffixes were accepted by the original release grammar.
        "2.7.1-.",
        "2.7.1--",
        "2.7.1+.",
        "2.7.1+-",
        "0" * 60 + ".0.0",
        "1.2.3+" + "a" * 58,
    ],
)
def test_is_release_version_accepts_existing_grammar(version: str) -> None:
    assert analytics._is_release_version(version)


@pytest.mark.parametrize(
    "version",
    [
        "",
        "1",
        "1.2",
        "1.2.3.4",
        ".2.3",
        "1..3",
        "1.2.",
        "v1.2.3",
        "1.2.3-",
        "1.2.3+",
        "1.2.3-+build",
        "1.2.3-rc+",
        "1.2.3++build",
        "1.2.3+build+extra",
        "1.2.3_rc",
        "1.2.3-rc_1",
        "1.2.3+build_1",
        " 1.2.3",
        "1.2.3 ",
        "1.2.3\n",
        "１.２.３",
        "١.٢.٣",
        "1.2.3-rélease",
        "1.2.3+构建",
        "0" * 63 + "!",
        "1.2." + "0" * 59 + "!",
        "1.2.3-" + "0" * 57 + "!",
        "0" * 61 + ".0.0",
        "1.2.3+" + "a" * 59,
        pytest.param("0" * 100_000 + "!", id="oversized-adversarial-version"),
    ],
)
def test_is_release_version_rejects_malformed_or_oversized_values(version: str) -> None:
    assert not analytics._is_release_version(version)


@pytest.mark.parametrize(
    ("version", "valid"),
    [
        ("001.02.003-rc.1+build.2", True),
        ("1.2.3+" + "a" * 58, True),
        ("1.2." + "0" * 59 + "!", False),
        ("1.2.3+" + "a" * 59, False),
    ],
)
def test_request_metadata_applies_bounded_release_validation(
    version: str, valid: bool
) -> None:
    app = Flask(__name__)
    app.add_url_rule("/api/shifu/shifus", endpoint="get_shifu_list_api")
    with app.test_request_context(
        "/api/shifu/shifus",
        headers={
            "X-AI-Shifu-Skill": analytics.SKILL_ID,
            "X-AI-Shifu-Skill-Version": version,
            "X-AI-Shifu-Caller-Agent": "codex",
            "X-AI-Shifu-Caller-Agent-Name": "Codex",
        },
    ):
        metadata = analytics._request_metadata()
        assert (metadata is not None) is valid
        if valid:
            assert metadata.version == version
