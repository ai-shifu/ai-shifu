from flask import Flask, request
from flaskr.route.common import make_common_response
from flaskr.service.order import success_buy_record



def register_order_handler(app: Flask, path_prefix: str):
     
    @app.route(path_prefix+'/order-test', methods=['POST'])
    def order_test():
        order_id = request.get_json().get('order_id', '')
        return make_common_response(success_buy_record(app, order_id))
    
    return app