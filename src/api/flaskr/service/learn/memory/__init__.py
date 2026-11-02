"""Moved to :mod:`flaskr.service.memory`; this alias keeps the old import path for one release."""

import importlib
import sys

from flaskr.service import memory

for _name in ("dtos", "facade", "reader"):
    sys.modules[f"{__name__}.{_name}"] = importlib.import_module(
        f"{memory.__name__}.{_name}"
    )

sys.modules[__name__] = memory
