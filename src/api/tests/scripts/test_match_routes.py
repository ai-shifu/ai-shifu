# Copyright 2026
"""Verify backend route inventory subprocess argument handling."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "inventory" / "match_routes.py"
)


def test_leading_dash_consumer_root_is_not_parsed_as_grep_option(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Keep a leading-dash consumer directory positional to grep."""
    inventory_dir = tmp_path / "inventory"
    inventory_dir.mkdir()
    (inventory_dir / "routes-backend.txt").write_text("", encoding="utf-8")

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    miniapp_dir = tmp_path / "-miniapp"
    miniapp_dir.mkdir()
    (miniapp_dir / "client.py").write_text(
        'PATH = "/api/leading-dash-consumer"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INVENTORY_WORK_DIR", str(inventory_dir))
    monkeypatch.setenv("SKILLS_REPO", str(skills_dir))
    monkeypatch.setenv("MINIAPP_REPO", "-miniapp")

    namespace = runpy.run_path(str(SCRIPT_PATH), run_name="__main__")

    assert ("api", "leading-dash-consumer") in namespace["surfaces"]["miniprogram"]
