from flaskr.service.order.funs import BuyRecordDTO


def test_buy_record_dto_json_includes_payment_payload():
    dto = BuyRecordDTO(
        record_id="order-1",
        user_id="user-1",
        price="99.00",
        channel="stripe:checkout_session",
        qr_url="https://checkout.stripe.com/c/pay/cs_test",
        payment_channel="stripe",
        payment_payload={"client_secret": "cs_test"},
    )

    payload = dto.__json__()

    assert payload["payment_channel"] == "stripe"
    assert payload["payment_payload"]["client_secret"] == "cs_test"
