

import dis


def test_discount(app):
    from  flaskr.service.order.discount import  generate_discount_code 
    from  flaskr.service.lesson.models import AICourse
    from flaskr.service.order.models import Discount
    with app.app_context():
        course = AICourse.query.first()
        course_id = course.course_id
        discount = Discount.query.first()
        if not discount:
            discount_id = generate_discount_code(app, 100, course_id, '2021-01-01', '2028-12-31', 'channel')
        else:
            pass

def test_create_discount(app):
    from  flaskr.service.order.discount import  generate_discount_code_by_rule 
    from  flaskr.service.order.models import Discount
    with app.app_context():
        discount = Discount.query.first()
        discount_id = discount.discount_id
        for i in range(10):
            generate_discount_code_by_rule(app, discount_id)




def test_buy_and_pay(app):
    from flaskr.service.order.funs import init_buy_record,generate_charge
    from flaskr.util.uuid import generate_id

    from flaskr.service.user.models import User
    from flaskr.service.lesson.models import AICourse
    from flaskr.service.order.models import DiscountRecord
    from flaskr.service.order.consts import DISCOUNT_STATUS_ACTIVE
    from flaskr.service.order.discount import  use_discount_code
    with app.app_context():
        user = User.query.first()
        course = AICourse.query.first()
        price = course.course_price
        user_id = user.user_id
        discount_record = DiscountRecord.query.filter(DiscountRecord.status == DISCOUNT_STATUS_ACTIVE).first()
        record = init_buy_record(app,user_id,course.course_id)
        use_discount_code(app, user_id, discount_record.discount_code, record.order_id)
        charge = generate_charge(app,
                                record.order_id,'alipay_qr','36.112.103.90')
        


         
