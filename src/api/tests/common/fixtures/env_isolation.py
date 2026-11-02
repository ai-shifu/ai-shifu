"""Undo-safe removal of registered config env vars for isolated tests."""

import os

import pytest
from flaskr.common.config import ENV_VARS


def clear_registered_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every registered config key with an undo entry, present or absent.

    Going through monkeypatch puts the isolation on the same LIFO undo stack as
    a test's own env patches, so it unwinds correctly whichever fixture created
    monkeypatch first. ``delenv`` records nothing for a key that is already
    absent, so each key is first set to its current value (recording the
    original, or its absence) and then deleted; a direct ``os.environ`` write
    during the test, such as one from ``Config.__setitem__``, is undone too.
    """
    for key in ENV_VARS:
        monkeypatch.setitem(os.environ, key, os.environ.get(key, ""))
        monkeypatch.delitem(os.environ, key)
