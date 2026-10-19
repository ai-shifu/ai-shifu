"""Keep attribute patches on a split module visible to its sibling modules.

Several large learn modules were split into cohesive siblings while keeping
every name importable from the original module path. Tests and operational
hooks patch dependencies on the original module (``monkeypatch.setattr(
context_v2, "db", ...)``); code that now lives in a sibling resolves its
globals in the sibling's namespace, so a plain patch would no longer reach it.

``forward_attribute_writes`` swaps the original module's class for a subclass
whose ``__setattr__`` also writes the value into every sibling that already
defines the same name. This mirrors the compatibility modules used by
``flaskr/service/shifu/admin.py`` and ``admin_operations/courses.py``.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def forward_attribute_writes(
    module_name: str,
    sibling_modules: Iterable[ModuleType],
) -> None:
    """Forward attribute writes on ``module_name`` to its split siblings."""
    targets = tuple(sibling_modules)

    class _SplitModule(ModuleType):
        def __setattr__(self, name: str, value: object) -> None:
            super().__setattr__(name, value)
            if name.startswith("__"):
                return
            for sibling in targets:
                if hasattr(sibling, name):
                    setattr(sibling, name, value)

    sys.modules[module_name].__class__ = _SplitModule
