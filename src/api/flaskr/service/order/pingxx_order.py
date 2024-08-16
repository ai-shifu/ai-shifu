from flask import Flask
import json
import pingpp
import os


def init_pingxx(app:Flask):
    app.logger.info('init pingxx')
    pingpp.api_key = app.config['PINGPP_SECRET_KEY']
    pingpp.private_key_path = app.config['PINGPP_PRIVATE_KEY_PATH']
    if os.path.exists(pingpp.private_key_path) == False:
        app.logger.error('private key not exists')
        return None
    app.logger.info('init pingxx done')
    return pingpp


def create_pingxx_order(app:Flask,order_no,app_id,channel,amount,client_ip,subject,body,extra=None):
    app.logger.info('create pingxx order,order_no:{} app_id:{} channel:{} amount:{} client_ip:{} subject:{} body:{} extra:{}'.format
                    (order_no,app_id,channel,amount,client_ip,subject,body,extra))
    pingpp = init_pingxx(app)
    order = pingpp.Charge.create(
        order_no=order_no,
        app=dict(id=app_id),
        channel=channel,
        amount=amount,
        client_ip=client_ip,
        currency='cny',
        subject=subject,
        body=body,
        extra=extra
    )
    app.logger.info('create pingxx order done')
    return order

def retrieve_pingxx_order(app:Flask,charge_id):
    app.logger.info('retrieve pingxx order,charge_id:{}'.format(charge_id))
    pingpp = init_pingxx(app)
    order = pingpp.Charge.retrieve(charge_id)
    app.logger.info('retrieve pingxx order done')
    return order
