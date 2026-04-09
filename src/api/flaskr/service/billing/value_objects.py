"""Shared internal value objects for typed billing service returns."""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Generic, TypeVar

from .models import BillingRenewalEvent, CreditWallet

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


@dataclass(slots=True, frozen=True)
class ProductCodeIndex:
    values: dict[str, str] = field(default_factory=dict)

    def get(self, product_bid: str, default: str = "") -> str:
        return self.values.get(product_bid, default)


@dataclass(slots=True, frozen=True)
class WalletIndex:
    values: dict[str, CreditWallet] = field(default_factory=dict)

    def get(self, creator_bid: str) -> CreditWallet | None:
        return self.values.get(creator_bid)


@dataclass(slots=True, frozen=True)
class RenewalEventIndex:
    values: dict[str, BillingRenewalEvent] = field(default_factory=dict)

    def get(self, subscription_bid: str) -> BillingRenewalEvent | None:
        return self.values.get(subscription_bid)


@dataclass(slots=True, frozen=True)
class UsageConsumedCreditIndex:
    values: dict[tuple[str, int], Decimal] = field(default_factory=dict)

    def get(self, usage_bid: str, metric_code: int, default: Decimal) -> Decimal:
        return self.values.get((usage_bid, metric_code), default)
