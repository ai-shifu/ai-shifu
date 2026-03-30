from flaskr.service.promo.models import CouponUsage as CouponUsageModel


def query_discount_record(order_id: str) -> list[CouponUsageModel]:
    return CouponUsageModel.query.filter(CouponUsageModel.order_bid == order_id).all()
