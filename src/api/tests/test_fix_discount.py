import pytest

pytest.skip(
    "Integration test requires existing orders/discount codes.",
    allow_module_level=True,
)


def test_fix_discount(app):
    from flaskr.service.order.discount import use_discount_code

    with app.app_context():
        order_id = "f989c12d5f2f44aa8b93b76c6b458437"
        user_id = "0957173df61046cb9d84e66c0d6123ae"
        use_discount_code(app, user_id, "JFJ4ZCHHYM1U", order_id)
