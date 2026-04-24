"""Shared internal value objects for typed billing service returns."""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True, frozen=True)
class PageWindow(Generic[T]):
    items: list[T]
    page: int
    page_count: int
    page_size: int
    total: int

    def to_dto_kwargs(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "page": self.page,
            "page_count": self.page_count,
            "page_size": self.page_size,
            "total": self.total,
        }


def _serialize_json_value(value: Any) -> Any:
    if isinstance(value, JsonObjectMap):
        return value.to_metadata_json()
    if isinstance(value, list):
        return [_serialize_json_value(item) for item in value]
    return value


@dataclass(slots=True)
class JsonObjectMap(MutableMapping[str, Any]):
    values: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.values[str(key)] = value

    def __delitem__(self, key: str) -> None:
        del self.values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def copy(self) -> "JsonObjectMap":
        return JsonObjectMap(values=dict(self.values))

    def to_metadata_json(self) -> dict[str, Any]:
        return {
            str(key): _serialize_json_value(value) for key, value in self.values.items()
        }
