"""Extension and plugin framework primitives."""

from .plugin.plugin_manager import (
    extensible,
    extensible_generic,
    extensible_generic_register,
    extension,
)

__all__ = [
    "extensible",
    "extensible_generic",
    "extensible_generic_register",
    "extension",
]
