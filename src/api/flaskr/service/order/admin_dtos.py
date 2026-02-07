from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from flaskr.common.swagger import register_schema_to_swagger


@register_schema_to_swagger
class OrderAdminSummaryDTO(BaseModel):
    """Summary information for an order in admin views."""

    order_bid: str = Field(..., description="Order business identifier", required=False)
    shifu_bid: str = Field(..., description="Shifu business identifier", required=False)
    shifu_name: str = Field(..., description="Shifu name", required=False)
    user_bid: str = Field(..., description="User business identifier", required=False)
    user_mobile: str = Field(..., description="User mobile", required=False)
    user_email: str = Field(..., description="User email", required=False)
    user_nickname: str = Field(..., description="User nickname", required=False)
    payable_price: str = Field(..., description="Payable price", required=False)
    paid_price: str = Field(..., description="Paid price", required=False)
    discount_amount: str = Field(..., description="Discount amount", required=False)
    status: int = Field(..., description="Order status", required=False)
    status_key: str = Field(..., description="Order status i18n key", required=False)
    payment_channel: str = Field(..., description="Payment channel", required=False)
    payment_channel_key: str = Field(
        ..., description="Payment channel i18n key", required=False
    )
    coupon_codes: List[str] = Field(
        default_factory=list,
        description="Coupon codes applied to this order",
        required=False,
    )
    created_at: str = Field(..., description="Created at", required=False)
    updated_at: str = Field(..., description="Updated at", required=False)

    def __init__(
        self,
        order_bid: str,
        shifu_bid: str,
        shifu_name: str,
        user_bid: str,
        user_mobile: str,
        user_email: str,
        user_nickname: str,
        payable_price: str,
        paid_price: str,
        discount_amount: str,
        status: int,
        status_key: str,
        payment_channel: str,
        payment_channel_key: str,
        created_at: str,
        updated_at: str,
        coupon_codes: List[str] | None = None,
    ):
        super().__init__(
            order_bid=order_bid,
            shifu_bid=shifu_bid,
            shifu_name=shifu_name,
            user_bid=user_bid,
            user_mobile=user_mobile,
            user_email=user_email,
            user_nickname=user_nickname,
            payable_price=payable_price,
            paid_price=paid_price,
            discount_amount=discount_amount,
            status=status,
            status_key=status_key,
            payment_channel=payment_channel,
            payment_channel_key=payment_channel_key,
            coupon_codes=coupon_codes or [],
            created_at=created_at,
            updated_at=updated_at,
        )

    def __json__(self):
        return {
            "order_bid": self.order_bid,
            "shifu_bid": self.shifu_bid,
            "shifu_name": self.shifu_name,
            "user_bid": self.user_bid,
            "user_mobile": self.user_mobile,
            "user_email": self.user_email,
            "user_nickname": self.user_nickname,
            "payable_price": self.payable_price,
            "paid_price": self.paid_price,
            "discount_amount": self.discount_amount,
            "status": self.status,
            "status_key": self.status_key,
            "payment_channel": self.payment_channel,
            "payment_channel_key": self.payment_channel_key,
            "coupon_codes": self.coupon_codes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@register_schema_to_swagger
class OrderAdminActivityDTO(BaseModel):
    """Activity participation info associated with an order."""

    active_id: str = Field(..., description="Active identifier", required=False)
    active_name: str = Field(..., description="Active name", required=False)
    price: str = Field(..., description="Active price", required=False)
    status: int = Field(..., description="Active status", required=False)
    status_key: str = Field(..., description="Active status i18n key", required=False)
    created_at: str = Field(..., description="Created at", required=False)
    updated_at: str = Field(..., description="Updated at", required=False)

    def __init__(
        self,
        active_id: str,
        active_name: str,
        price: str,
        status: int,
        status_key: str,
        created_at: str,
        updated_at: str,
    ):
        super().__init__(
            active_id=active_id,
            active_name=active_name,
            price=price,
            status=status,
            status_key=status_key,
            created_at=created_at,
            updated_at=updated_at,
        )

    def __json__(self):
        return {
            "active_id": self.active_id,
            "active_name": self.active_name,
            "price": self.price,
            "status": self.status,
            "status_key": self.status_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@register_schema_to_swagger
class OrderAdminCouponDTO(BaseModel):
    """Coupon usage detail associated with an order."""

    coupon_bid: str = Field(..., description="Coupon identifier", required=False)
    code: str = Field(..., description="Coupon code", required=False)
    name: str = Field(..., description="Coupon name", required=False)
    discount_type: int = Field(..., description="Discount type", required=False)
    discount_type_key: str = Field(
        ..., description="Discount type i18n key", required=False
    )
    value: str = Field(..., description="Discount value", required=False)
    status: int = Field(..., description="Coupon status", required=False)
    status_key: str = Field(..., description="Coupon status i18n key", required=False)
    created_at: str = Field(..., description="Created at", required=False)
    updated_at: str = Field(..., description="Updated at", required=False)

    def __init__(
        self,
        coupon_bid: str,
        code: str,
        name: str,
        discount_type: int,
        discount_type_key: str,
        value: str,
        status: int,
        status_key: str,
        created_at: str,
        updated_at: str,
    ):
        super().__init__(
            coupon_bid=coupon_bid,
            code=code,
            name=name,
            discount_type=discount_type,
            discount_type_key=discount_type_key,
            value=value,
            status=status,
            status_key=status_key,
            created_at=created_at,
            updated_at=updated_at,
        )

    def __json__(self):
        return {
            "coupon_bid": self.coupon_bid,
            "code": self.code,
            "name": self.name,
            "discount_type": self.discount_type,
            "discount_type_key": self.discount_type_key,
            "value": self.value,
            "status": self.status,
            "status_key": self.status_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@register_schema_to_swagger
class OrderAdminPaymentDTO(BaseModel):
    """Payment information for an order including channel-specific fields."""

    payment_channel: str = Field(..., description="Payment channel", required=False)
    payment_channel_key: str = Field(
        ..., description="Payment channel i18n key", required=False
    )
    status: int = Field(..., description="Payment status", required=False)
    status_key: str = Field(..., description="Payment status i18n key", required=False)
    amount: str = Field(..., description="Payment amount", required=False)
    currency: str = Field(..., description="Payment currency", required=False)
    payment_intent_id: str = Field(
        ..., description="Stripe payment intent id", required=False
    )
    checkout_session_id: str = Field(
        ..., description="Stripe checkout session id", required=False
    )
    latest_charge_id: str = Field(
        ..., description="Stripe latest charge id", required=False
    )
    receipt_url: str = Field(..., description="Stripe receipt url", required=False)
    payment_method: str = Field(
        ..., description="Stripe payment method", required=False
    )
    transaction_no: str = Field(
        ..., description="Pingxx transaction number", required=False
    )
    charge_id: str = Field(..., description="Pingxx charge id", required=False)
    channel: str = Field(..., description="Pingxx channel", required=False)
    created_at: str = Field(..., description="Created at", required=False)
    updated_at: str = Field(..., description="Updated at", required=False)

    def __init__(
        self,
        payment_channel: str,
        payment_channel_key: str,
        status: int,
        status_key: str,
        amount: str,
        currency: str,
        payment_intent_id: str = "",
        checkout_session_id: str = "",
        latest_charge_id: str = "",
        receipt_url: str = "",
        payment_method: str = "",
        transaction_no: str = "",
        charge_id: str = "",
        channel: str = "",
        created_at: str = "",
        updated_at: str = "",
    ):
        super().__init__(
            payment_channel=payment_channel,
            payment_channel_key=payment_channel_key,
            status=status,
            status_key=status_key,
            amount=amount,
            currency=currency,
            payment_intent_id=payment_intent_id,
            checkout_session_id=checkout_session_id,
            latest_charge_id=latest_charge_id,
            receipt_url=receipt_url,
            payment_method=payment_method,
            transaction_no=transaction_no,
            charge_id=charge_id,
            channel=channel,
            created_at=created_at,
            updated_at=updated_at,
        )

    def __json__(self):
        return {
            "payment_channel": self.payment_channel,
            "payment_channel_key": self.payment_channel_key,
            "status": self.status,
            "status_key": self.status_key,
            "amount": self.amount,
            "currency": self.currency,
            "payment_intent_id": self.payment_intent_id,
            "checkout_session_id": self.checkout_session_id,
            "latest_charge_id": self.latest_charge_id,
            "receipt_url": self.receipt_url,
            "payment_method": self.payment_method,
            "transaction_no": self.transaction_no,
            "charge_id": self.charge_id,
            "channel": self.channel,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@register_schema_to_swagger
class OrderAdminDetailDTO(BaseModel):
    """Full order detail bundle returned to admin clients."""

    order: OrderAdminSummaryDTO = Field(
        ..., description="Order summary", required=False
    )
    activities: List[OrderAdminActivityDTO] = Field(
        ..., description="Order activities", required=False
    )
    coupons: List[OrderAdminCouponDTO] = Field(
        ..., description="Order coupons", required=False
    )
    payment: OrderAdminPaymentDTO = Field(
        ..., description="Payment detail", required=False
    )

    def __init__(
        self,
        order: OrderAdminSummaryDTO,
        activities: List[OrderAdminActivityDTO],
        coupons: List[OrderAdminCouponDTO],
        payment: OrderAdminPaymentDTO,
    ):
        super().__init__(
            order=order,
            activities=activities,
            coupons=coupons,
            payment=payment,
        )

    def __json__(self):
        return {
            "order": self.order,
            "activities": self.activities,
            "coupons": self.coupons,
            "payment": self.payment,
        }
