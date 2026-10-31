"""Moved to :mod:`flaskr.service.learn.ask.providers`; this alias keeps the old import path for one release.

Submodules are aliased too, so ``ask_provider_adapters.<name>`` resolves to the
same module object instead of loading the file a second time.
"""

import importlib
import sys

from flaskr.service.learn.ask import providers

for _name in (
    "base",
    "common",
    "consts",
    "coze_adapter",
    "coze_workflow_adapter",
    "dify_adapter",
    "get_biji_knowledge_adapter",
    "llm_adapter",
    "registry",
    "volc_knowledge_adapter",
):
    sys.modules[f"{__name__}.{_name}"] = importlib.import_module(
        f"{providers.__name__}.{_name}"
    )

sys.modules[__name__] = providers
