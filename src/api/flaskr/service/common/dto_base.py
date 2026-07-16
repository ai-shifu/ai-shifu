"""Auto-generated ``__json__`` support for pydantic API DTOs.

The API response sink (``json.dumps(..., default=fmt)`` in
``flaskr/route/common.py``) serializes DTOs by calling their ``__json__``
method; ``fmt`` itself handles ``datetime`` (UTC ISO-8601 with a ``Z``
suffix), ``date``, and ``Decimal`` leaf values. Historically every DTO wrote
``__json__`` by hand. :class:`AutoJsonMixin` generates an equivalent
``__json__`` from the pydantic field declarations so the hand-written copies
can be deleted without changing a single output byte.

Migration is INCREMENTAL: convert one DTO module at a time and prove
byte-identical ``json.dumps`` output before landing. Converted so far:

- ``flaskr/service/dashboard/dtos.py`` (pilot, 18 classes)

How per-class output is reproduced:

- Keys default to the pydantic field names in declaration order, which is
  what the vast majority of hand-written ``__json__`` dicts emit (snake_case
  today; a camelCase class would set ``__json_key_overrides__``).
- ``__json_key_overrides__`` maps field name -> output key for classes whose
  JSON keys differ from field names (e.g. ``data`` -> ``items``).
- ``__json_exclude__`` lists declared fields the hand-written ``__json__``
  omitted from the payload.
- Plain ``int`` / ``bool`` annotated fields are passed through ``int()`` /
  ``bool()`` exactly like the hand-written implementations did.
- Nested DTOs (and lists of DTOs) are serialized via their own ``__json__``;
  ``datetime`` / ``Decimal`` / ``None`` leaves are emitted raw so the ``fmt``
  sink keeps owning their string contract.
"""

from __future__ import annotations

from typing import Any


def _json_field_value(value: Any, annotation: Any) -> Any:
    """Convert one field value the same way hand-written ``__json__`` did."""
    if annotation is int:
        return int(value)
    if annotation is bool:
        return bool(value)
    if hasattr(value, "__json__"):
        return value.__json__()
    if isinstance(value, list):
        return [
            item.__json__() if hasattr(item, "__json__") else item for item in value
        ]
    return value


class AutoJsonMixin:
    """Mixin that derives ``__json__`` from pydantic field declarations.

    Mix into a ``pydantic.BaseModel`` subclass (``class MyDTO(AutoJsonMixin,
    BaseModel)``). See the module docstring for the reproduction rules and
    the per-class knobs ``__json_key_overrides__`` and ``__json_exclude__``.
    """

    __json_key_overrides__: dict = {}
    __json_exclude__: frozenset = frozenset()

    def __json__(self) -> dict:
        payload = {}
        for name, field in type(self).model_fields.items():
            if name in self.__json_exclude__:
                continue
            key = self.__json_key_overrides__.get(name, name)
            payload[key] = _json_field_value(getattr(self, name), field.annotation)
        return payload
