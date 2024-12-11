from flask import Flask
from flaskr.service.order.models import DiscountRecord


def query_discount_record(app: Flask, order_id):
    return DiscountRecord.query.filter(DiscountRecord.order_id == order_id).all()
