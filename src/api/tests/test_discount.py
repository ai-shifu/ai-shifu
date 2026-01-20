from flaskr.service.order.coupon_funcs import (
    _coupon_matches_course,
    _get_course_id_from_filter,
    _pick_coupon_candidate,
)
from flaskr.service.promo.models import Coupon, CouponUsage


def _make_coupon(course_id: str | None = None) -> Coupon:
    coupon = Coupon()
    if course_id is None:
        coupon.filter = ""
    else:
        coupon.filter = f'{{"course_id": "{course_id}"}}'
    coupon.coupon_bid = "coupon-1"
    coupon.code = "CODE"
    return coupon


def _make_usage(user_id: str, coupon_bid: str) -> CouponUsage:
    usage = CouponUsage()
    usage.user_bid = user_id
    usage.coupon_bid = coupon_bid
    return usage


def test_get_course_id_from_filter_handles_invalid_json():
    coupon = Coupon()
    coupon.filter = "not-json"
    assert _get_course_id_from_filter(coupon) is None


def test_coupon_matches_course_when_filter_missing():
    coupon = _make_coupon(None)
    assert _coupon_matches_course(coupon, "course-1") is True


def test_coupon_matches_course_when_filter_matches():
    coupon = _make_coupon("course-1")
    assert _coupon_matches_course(coupon, "course-1") is True
    assert _coupon_matches_course(coupon, "course-2") is False


def test_pick_coupon_candidate_prefers_user_usage():
    coupon = _make_coupon("course-1")
    usage = _make_usage("user-1", coupon.coupon_bid)
    other_usage = _make_usage("user-2", coupon.coupon_bid)

    usage_result, coupon_result, has_candidate = _pick_coupon_candidate(
        [usage, other_usage],
        {coupon.coupon_bid: coupon},
        [],
        "course-1",
        "user-1",
    )

    assert usage_result is usage
    assert coupon_result is coupon
    assert has_candidate is True


def test_pick_coupon_candidate_falls_back_to_code_coupon():
    coupon = _make_coupon("course-1")
    usage_result, coupon_result, has_candidate = _pick_coupon_candidate(
        [],
        {},
        [coupon],
        "course-1",
        "user-1",
    )

    assert usage_result is None
    assert coupon_result is coupon
    assert has_candidate is True
