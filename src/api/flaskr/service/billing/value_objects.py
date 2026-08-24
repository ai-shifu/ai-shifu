"""Shared internal value objects for typed billing service returns."""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True, frozen=True)
class PageWindow(Generic[T]):
    """Describe the offset and size of one result page."""

    items: list[T]
    page: int
    page_count: int
    page_size: int
    total: int

    def to_dto_kwargs(self) -> dict[str, Any]:
        """Return keyword arguments for the page-window DTO."""
        return {
            "items": self.items,
            "page": self.page,
            "page_count": self.page_count,
            "page_size": self.page_size,
            "total": self.total,
        }


def _serialize_json_value(value: object) -> object:
    if isinstance(value, JsonObjectMap):
        return value.to_metadata_json()
    if isinstance(value, list):
        return [_serialize_json_value(item) for item in value]
    return value


@dataclass(slots=True)
class JsonObjectMap(MutableMapping[str, Any]):
    """Map string keys to JSON-compatible object values."""

    values: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> object:
        """Return a stored JSON value by key."""
        return self.values[key]

    def __setitem__(self, key: str, value: object) -> None:
        """Store a JSON value under the normalized string key."""
        self.values[str(key)] = value

    def __delitem__(self, key: str) -> None:
        """Delete the stored JSON value for a key."""
        del self.values[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate over the stored JSON keys."""
        return iter(self.values)

    def __len__(self) -> int:
        """Return the number of stored JSON keys."""
        return len(self.values)

    def get(self, key: str, default: object = None) -> object:
        """Return the stored value for a key."""
        return self.values.get(key, default)

    def copy(self) -> JsonObjectMap:
        """Return a shallow copy of this JSON object map."""
        return JsonObjectMap(values=dict(self.values))

    def __json__(self) -> dict[str, Any]:
        """Serialize this value for the shared JSON response formatter."""
        return self.to_metadata_json()

    def to_metadata_json(self) -> dict[str, Any]:
        """Serialize this value as JSON-compatible metadata."""
        return {
            str(key): _serialize_json_value(value) for key, value in self.values.items()
        }
