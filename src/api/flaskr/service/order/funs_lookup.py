"""Late-bound access to ``flaskr.service.order.funs`` for its split-out helpers.

``funs`` was split into sibling modules, but tests and plugins still patch
collaborators such as ``get_payment_provider`` or ``unit_of_work`` on
``flaskr.service.order.funs``. The split-out modules look those names up
through ``order_funs`` at call time, exactly as the original module-level
global lookups did, so such patches keep applying. It also lets them call
helpers that still live in ``funs`` without a circular import.
"""

from importlib import import_module


class _OrderFunsModule:
    """Resolve attributes on ``flaskr.service.order.funs`` when accessed."""

    def __getattr__(self, name: str) -> object:
        return getattr(import_module("flaskr.service.order.funs"), name)


order_funs = _OrderFunsModule()
