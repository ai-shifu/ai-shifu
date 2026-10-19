"""Define the legacy order and payment DTOs returned by order services."""

import decimal

from flaskr.common.swagger import register_schema_to_swagger
from flaskr.service.order.consts import (
    ORDER_STATUS_VALUES,
)


@register_schema_to_swagger
class PayItemDto:
    """PayItemDto."""

    name: str
    price_name: str
    price: str
    is_discount: bool
    discount_code: str

    def __init__(
        self,
        name: object,
        price_name: object,
        price: object,
        is_discount: object,
        discount_code: object,
    ) -> None:
        """Build the pay item payload."""
        self.name = name
        self.price_name = price_name
        self.price = price
        self.is_discount = is_discount
        self.discount_code = discount_code

    def __json__(self) -> dict:
        """Return the pay item as JSON-compatible data."""
        return {
            "name": self.name,
            "price_name": self.price_name,
            "price": str(self.price),
            "is_discount": self.is_discount,
        }


@register_schema_to_swagger
class AICourseBuyRecordDTO:
    """AICourseBuyRecordDTO."""

    order_id: str
    user_id: str
    course_id: str
    price: decimal.Decimal
    status: int
    discount: str
    active_discount: str
    value_to_pay: str
    price_item: list[PayItemDto]

    def __init__(
        self,
        record_id: object,
        user_id: object,
        course_id: object,
        price: object,
        status: object,
        discount: object,
        price_item: object,
        payment_channel: object = "",
    ) -> None:
        """Build the AI course buy record payload."""
        self.order_id = record_id
        self.user_id = user_id
        self.course_id = course_id
        self.price = price
        self.status = status
        self.discount = discount
        self.value_to_pay = str(decimal.Decimal(price) - decimal.Decimal(discount))
        self.price_item = price_item
        self.payment_channel = payment_channel

    def __json__(self) -> dict:
        """Return the AI course buy record as JSON-compatible data."""

        def format_decimal(value: object) -> str:
            # Convert to a string with two decimal places
            formatted_value = value if isinstance(value, str) else f"{value:.2f}"
            # If the decimal part is .00, remove it
            if formatted_value.endswith(".00"):
                return formatted_value[:-3]
            return formatted_value

        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "course_id": self.course_id,
            "price": format_decimal(self.price),
            "status": self.status,
            "status_desc": ORDER_STATUS_VALUES[self.status],
            "discount": format_decimal(self.discount),
            "value_to_pay": format_decimal(self.value_to_pay),
            "price_item": [item.__json__() for item in self.price_item],
        }


@register_schema_to_swagger
class BuyRecordDTO:
    """BuyRecordDTO."""

    order_id: str
    user_id: str  # 用户id
    price: str  # 价格
    channel: str  # 支付渠道
    qr_url: str  # 二维码地址

    def __init__(
        self,
        record_id: object,
        user_id: object,
        price: object,
        channel: object,
        qr_url: object,
        payment_channel: str = "",
        payment_payload: dict[str, object] | None = None,
    ) -> None:
        """Build the buy record payload."""
        self.order_id = record_id
        self.user_id = user_id
        self.price = price
        self.channel = channel
        self.qr_url = qr_url
        self.payment_channel = payment_channel
        self.payment_payload = payment_payload or {}

    def __json__(self) -> dict:
        """Return the buy record as JSON-compatible data."""
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "price": str(self.price),
            "channel": self.channel,
            "qr_url": self.qr_url,
            "payment_channel": self.payment_channel,
            "payment_payload": self.payment_payload,
        }


class DiscountInfo:
    """Describe discounts applied to an order."""

    discount_value: str
    items: list[PayItemDto]

    def __init__(self, discount_value: object, items: object) -> None:
        """Capture the discount value and affected payment items."""
        self.discount_value = discount_value
        self.items = items
