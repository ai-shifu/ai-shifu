"""Helpers for keeping renamed public names importable during a transition."""

import warnings
from collections.abc import Callable


def deprecated_alias_getattr(
    module_name: str, aliases: dict[str, str], namespace: dict[str, object]
) -> Callable[[str], object]:
    """Build a module ``__getattr__`` that resolves renamed names with a warning.

    ``aliases`` maps a removed name to its current name in ``namespace``.
    """

    def module_getattr(name: str) -> object:
        current = aliases.get(name)
        if current is None:
            message = f"module {module_name!r} has no attribute {name!r}"
            raise AttributeError(message)
        warnings.warn(
            f"{module_name}.{name} is deprecated, use {current} instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return namespace[current]

    return module_getattr
