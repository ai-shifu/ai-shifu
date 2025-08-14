from flask import Flask
from flaskr.service.order.models import CouponUsage as CouponUsageModel


def query_discount_record(
    app: Flask, order_id: str, recaul_discount: bool
) -> list[CouponUsageModel]:
    return CouponUsageModel.query.filter(CouponUsageModel.order_bid == order_id).all()
