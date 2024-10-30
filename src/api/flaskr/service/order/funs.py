import datetime
import decimal
import json
from typing import List


from flaskr.service.order.consts import (
    ATTEND_STATUS_LOCKED,
    ATTEND_STATUS_NOT_STARTED,
    BUY_STATUS_INIT,
    BUY_STATUS_SUCCESS,
    BUY_STATUS_TO_BE_PAID,
    BUY_STATUS_VALUES,
)
from flaskr.service.common.dtos import USER_STATE_PAID, USER_STATE_REGISTERED
from flaskr.service.user.models import User, UserConversion
from flaskr.service.active import query_active_record, query_and_join_active
from flaskr.service.order.query_discount import query_discount_record
from flaskr.common.swagger import register_schema_to_swagger
from flaskr.api.doc.feishu import send_notify
from .models import AICourseBuyRecord, PingxxOrder
from flask import Flask
from ...dao import db, redis_client
from ..common.models import (
    raise_error,
)
from ..lesson.models import AICourse, AILesson
from .models import AICourseLessonAttend
from ...util.uuid import generate_id as get_uuid
from ..lesson.const import LESSON_TYPE_TRIAL
from .pingxx_order import create_pingxx_order


@register_schema_to_swagger
class AICourseLessonAttendDTO:
    attend_id: str
    lesson_id: str
    course_id: str
    user_id: str
    status: int
    index: int

    def __init__(self, attend_id, lesson_id, course_id, user_id, status, index):
        self.attend_id = attend_id
        self.lesson_id = lesson_id
        self.course_id = course_id
        self.user_id = user_id
        self.status = status
        self.index = index

    def __json__(self):
        return {
            "attend_id": self.attend_id,
            "lesson_id": self.lesson_id,
            "course_id": self.course_id,
            "user_id": self.user_id,
            "status": self.status,
            "index": self.index,
        }


@register_schema_to_swagger
class PayItemDto:
    name: str
    price_name: str
    price: str
    is_discount: bool
    discount_code: str

    def __init__(self, name, price_name, price, is_discount, discount_code):
        self.name = name
        self.price_name = price_name
        self.price = price
        self.is_discount = is_discount
        self.discount_code = discount_code

    def __json__(self):
        return {
            "name": self.name,
            "price_name": self.price_name,
            "price": str(self.price),
            "is_discount": self.is_discount,
        }


@register_schema_to_swagger
class AICourseBuyRecordDTO:
    order_id: str
    user_id: str
    course_id: str
    price: str
    status: int
    discount: str
    active_discount: str
    value_to_pay: str
    price_item: List[PayItemDto]

    def __init__(
        self, record_id, user_id, course_id, price, status, discount, price_item
    ):
        self.order_id = record_id
        self.user_id = user_id
        self.course_id = course_id
        self.price = price
        self.status = status
        self.discount = discount
        self.value_to_pay = str(decimal.Decimal(price) - decimal.Decimal(discount))
        self.price_item = price_item

    def __json__(self):
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "course_id": self.course_id,
            "price": str(self.price),
            "status": self.status,
            "status_desc": BUY_STATUS_VALUES[self.status],
            "discount": str(self.discount),
            "value_to_pay": str(self.value_to_pay),
            "price_item": [item.__json__() for item in self.price_item],
        }


def send_order_feishu(app: Flask, record_id: str):
    order_info = query_buy_record(app, record_id)
    urser_info = User.query.filter(User.user_id == order_info.user_id).first()
    if not urser_info:
        return
    title = "购买课程通知"
    msgs = []
    msgs.append("手机号：{}".format(urser_info.mobile))
    msgs.append("昵称：{}".format(urser_info.name))
    msgs.append("课程名称：{}".format(order_info.course_id))
    msgs.append("实付金额：{}".format(order_info.value_to_pay))
    user_convertion = UserConversion.query.filter(
        UserConversion.user_id == order_info.user_id
    ).first()
    channel = ""
    if user_convertion:
        channel = user_convertion.conversion_source
    msgs.append("渠道：{}".format(channel))
    for item in order_info.price_item:
        msgs.append("{}-{}-{}".format(item.name, item.price_name, item.price))
        if item.is_discount:
            msgs.append("优惠码：{}".format(item.discount_code))
    user_count = User.query.filter(User.user_state == USER_STATE_PAID).count()
    msgs.append("总付费用户数：{}".format(user_count))
    user_reg_count = User.query.filter(User.user_state >= USER_STATE_REGISTERED).count()
    msgs.append("总注册用户数：{}".format(user_reg_count))
    user_total_count = User.query.count()
    msgs.append("总访客数：{}".format(user_total_count))
    send_notify(app, title, msgs)


def init_buy_record(app: Flask, user_id: str, course_id: str):
    with app.app_context():
        course_info = AICourse.query.filter(AICourse.course_id == course_id).first()
        if not course_info:
            raise_error("LESSON.COURSE_NOT_FOUND")
        origin_record = (
            AICourseBuyRecord.query.filter(
                AICourseBuyRecord.user_id == user_id,
                AICourseBuyRecord.course_id == course_id,
            )
            .order_by(AICourseBuyRecord.id.asc())
            .first()
        )
        if origin_record:
            return query_buy_record(app, origin_record.record_id)

        order_id = str(get_uuid(app))
        active_records = query_and_join_active(app, course_id, user_id, order_id)
        buy_record = AICourseBuyRecord()
        buy_record.user_id = user_id
        buy_record.course_id = course_id
        buy_record.price = course_info.course_price
        buy_record.status = BUY_STATUS_INIT
        buy_record.record_id = order_id
        buy_record.discount_value = decimal.Decimal(0.00)
        buy_record.pay_value = course_info.course_price
        price_items = []
        price_items.append(
            PayItemDto("商品", "基础价格", buy_record.price, False, None)
        )
        if active_records:
            for active_record in active_records:
                buy_record.discount_value = decimal.Decimal(
                    buy_record.discount_value
                ) + decimal.Decimal(active_record.price)
                price_items.append(
                    PayItemDto(
                        "活动",
                        active_record.active_name,
                        active_record.price,
                        True,
                        None,
                    )
                )
        buy_record.pay_value = decimal.Decimal(buy_record.price) - decimal.Decimal(
            buy_record.discount_value
        )
        db.session.add(buy_record)
        db.session.commit()
        return AICourseBuyRecordDTO(
            buy_record.record_id,
            buy_record.user_id,
            buy_record.course_id,
            buy_record.price,
            buy_record.status,
            buy_record.discount_value,
            price_items,
        )


@register_schema_to_swagger
class BuyRecordDTO:
    order_id: str
    user_id: str  # 用户id
    price: str  # 价格
    channel: str  # 支付渠道
    qr_url: str  # 二维码地址

    def __init__(self, record_id, user_id, price, channel, qr_url):
        self.order_id = record_id
        self.user_id = user_id
        self.price = price
        self.channel = channel
        self.qr_url = qr_url

    def __json__(self):
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "price": str(self.price),
            "channel": self.channel,
            "qr_url": self.qr_url,
        }


def generate_charge(
    app: Flask, record_id: str, channel: str, client_ip: str
) -> BuyRecordDTO:
    with app.app_context():
        app.logger.info(
            "generate charge for record:{} channel:{}".format(record_id, channel)
        )

        buy_record = AICourseBuyRecord.query.filter(
            AICourseBuyRecord.record_id == record_id
        ).first()
        if not buy_record:
            raise_error("ORDER.ORDER_NOT_FOUND")
        course = AICourse.query.filter(
            AICourse.course_id == buy_record.course_id
        ).first()
        if not course:
            raise_error("COURSE.COURSE_NOT_FOUND")
        app.logger.info("buy record found:{}".format(buy_record))
        if buy_record.status == BUY_STATUS_SUCCESS:
            app.logger.error("buy record:{} status is not init".format(record_id))
            raise_error("ORDER.ORDER_HAS_PAID")
        amount = int(buy_record.pay_value * 100)
        product_id = course.course_id
        subject = course.course_name
        body = course.course_name
        order_no = str(get_uuid(app))
        qr_url = None
        pingpp_id = app.config.get("PINGPP_APP_ID")
        if amount == 0:
            success_buy_record(app, buy_record.record_id)
            return BuyRecordDTO(
                buy_record.record_id,
                buy_record.user_id,
                buy_record.price,
                channel,
                qr_url,
            )
        if channel == "wx_pub_qr":  # wxpay scan
            extra = dict({"product_id": product_id})
            charge = create_pingxx_order(
                app,
                order_no,
                pingpp_id,
                channel,
                amount,
                client_ip,
                subject,
                body,
                extra,
            )
            qr_url = charge["credential"]["wx_pub_qr"]
        elif channel == "alipay_qr":  # alipay scan
            extra = dict({})
            charge = create_pingxx_order(
                app,
                order_no,
                pingpp_id,
                channel,
                amount,
                client_ip,
                subject,
                body,
                extra,
            )
            qr_url = charge["credential"]["alipay_qr"]
        elif channel == "wx_pub":  # wxpay JSAPI
            user = User.query.filter(User.user_id == buy_record.user_id).first()
            extra = dict({"open_id": user.user_open_id})
            charge = create_pingxx_order(
                app,
                order_no,
                pingpp_id,
                channel,
                amount,
                client_ip,
                subject,
                body,
                extra,
            )
            qr_url = charge["credential"]["wx_pub"]
        elif channel == "wx_wap":  # wxpay H5
            extra = dict({})
            charge = create_pingxx_order(
                app,
                order_no,
                pingpp_id,
                channel,
                amount,
                client_ip,
                subject,
                body,
                extra,
            )
        else:
            app.logger.error("channel:{} not support".format(channel))
            raise_error("PAY.PAY_CHANNEL_NOT_SUPPORT")
        app.logger.info("charge created:{}".format(charge))
        buy_record.status = BUY_STATUS_TO_BE_PAID
        pingxxOrder = PingxxOrder()
        pingxxOrder.order_id = order_no
        pingxxOrder.user_id = buy_record.user_id
        pingxxOrder.course_id = buy_record.course_id
        pingxxOrder.record_id = buy_record.record_id
        pingxxOrder.pingxx_transaction_no = charge["transaction_no"]
        pingxxOrder.pingxx_app_id = charge["app"]
        pingxxOrder.pingxx_channel = charge["channel"]
        pingxxOrder.pingxx_id = charge["id"]
        pingxxOrder.channel = charge["channel"]
        pingxxOrder.amount = amount
        pingxxOrder.currency = charge["currency"]
        pingxxOrder.subject = charge["subject"]
        pingxxOrder.body = charge["body"]
        pingxxOrder.order_no = charge["order_no"]
        pingxxOrder.client_ip = charge["client_ip"]
        pingxxOrder.extra = str(charge["extra"])
        pingxxOrder.charge_id = charge["id"]
        pingxxOrder.status = 0
        pingxxOrder.charge_object = str(charge)
        db.session.add(pingxxOrder)
        db.session.commit()
        return BuyRecordDTO(
            buy_record.record_id, buy_record.user_id, buy_record.price, channel, qr_url
        )


def success_buy_record_from_pingxx(app: Flask, charge_id: str, body: dict):
    with app.app_context():
        lock = redis_client.lock(
            "success_buy_record_from_pingxx" + charge_id,
            timeout=10,
            blocking_timeout=10,
        )

        if not lock:
            app.logger.error('lock failed for charge:"{}"'.format(charge_id))
        if lock.acquire(blocking=True):
            try:
                app.logger.info(
                    'success buy record from pingxx charge:"{}"'.format(charge_id)
                )
                pingxx_order = PingxxOrder.query.filter(
                    PingxxOrder.charge_id == charge_id
                ).first()
                pingxx_order.update = datetime.datetime.now()
                pingxx_order.status = 1
                pingxx_order.charge_object = json.dumps(body)
                if pingxx_order:
                    buy_record = AICourseBuyRecord.query.filter(
                        AICourseBuyRecord.record_id == pingxx_order.record_id
                    ).first()

                    if buy_record and buy_record.status == BUY_STATUS_TO_BE_PAID:
                        try:
                            user_info = User.query.filter(
                                User.user_id == buy_record.user_id
                            ).first()
                            if not user_info:
                                app.logger.error(
                                    "user:{} not found".format(buy_record.user_id)
                                )
                            user_info.user_state = USER_STATE_PAID
                        except Exception as e:
                            app.logger.error("update user state error:{}".format(e))
                        buy_record.status = BUY_STATUS_SUCCESS
                        lessons = AILesson.query.filter(
                            AILesson.course_id == buy_record.course_id,
                            AILesson.status == 1,
                            AILesson.lesson_type != LESSON_TYPE_TRIAL,
                        ).all()
                        for lesson in lessons:
                            app.logger.info(
                                "init lesson attend for user:{} lesson:{}".format(
                                    buy_record.user_id, lesson.lesson_id
                                )
                            )
                            attend = AICourseLessonAttend.query.filter(
                                AICourseLessonAttend.user_id == buy_record.user_id,
                                AICourseLessonAttend.lesson_id == lesson.lesson_id,
                            ).first()
                            if attend:
                                continue
                            attend = AICourseLessonAttend()
                            attend.attend_id = str(get_uuid(app))
                            attend.course_id = buy_record.course_id
                            attend.lesson_id = lesson.lesson_id
                            attend.user_id = buy_record.user_id
                            if lesson.lesson_no in ["01", "0101"]:
                                attend.status = ATTEND_STATUS_NOT_STARTED
                            else:
                                attend.status = ATTEND_STATUS_LOCKED
                            db.session.add(attend)
                        db.session.commit()
                        send_order_feishu(app, buy_record.record_id)
                        return query_buy_record(app, buy_record.record_id)
                    else:
                        app.logger.error(
                            "record:{} not found".format(pingxx_order.record_id)
                        )
                else:
                    app.logger.error("charge:{} not found".format(charge_id))
                return None
            except Exception as e:
                app.logger.error(
                    'success buy record from pingxx charge:"{}" error:{}'.format(
                        charge_id, e
                    )
                )
            finally:
                lock.release()


def success_buy_record(app: Flask, record_id: str):
    with app.app_context():
        app.logger.info('success buy record:"{}"'.format(record_id))
        buy_record = AICourseBuyRecord.query.filter(
            AICourseBuyRecord.record_id == record_id
        ).first()
        if buy_record:
            user_info = User.query.filter(User.user_id == buy_record.user_id).first()
            if not user_info:
                app.logger.error("user:{} not found".format(buy_record.user_id))
                user_info.user_state = USER_STATE_PAID
            buy_record.status = BUY_STATUS_SUCCESS
            lessons = AILesson.query.filter(
                AILesson.course_id == buy_record.course_id,
                AILesson.status == 1,
                AILesson.lesson_type != LESSON_TYPE_TRIAL,
            ).all()
            for lesson in lessons:
                app.logger.info(
                    "init lesson attend for user:{} lesson:{}".format(
                        buy_record.user_id, lesson.lesson_id
                    )
                )
                attend = AICourseLessonAttend.query.filter(
                    AICourseLessonAttend.user_id == buy_record.user_id,
                    AICourseLessonAttend.lesson_id == lesson.lesson_id,
                ).first()
                if attend:
                    continue
                attend = AICourseLessonAttend()
                attend.attend_id = str(get_uuid(app))
                attend.course_id = buy_record.course_id
                attend.lesson_id = lesson.lesson_id
                attend.user_id = buy_record.user_id
                if lesson.lesson_no in ["01", "0101"]:
                    attend.status = ATTEND_STATUS_NOT_STARTED
                else:
                    attend.status = ATTEND_STATUS_LOCKED
                db.session.add(attend)
            db.session.commit()
            send_order_feishu(app, buy_record.record_id)
            return query_buy_record(app, record_id)
        else:
            app.logger.error("record:{} not found".format(record_id))
        return None


def init_trial_lesson(
    app: Flask, user_id: str, course_id: str
) -> list[AICourseLessonAttendDTO]:
    app.logger.info(
        "init trial lesson for user:{} course:{}".format(user_id, course_id)
    )
    response = []
    lessons = AILesson.query.filter(
        AILesson.course_id == course_id,
        AILesson.lesson_type == LESSON_TYPE_TRIAL,
        AILesson.status == 1,
    ).all()
    app.logger.info("init trial lesson:{}".format(lessons))
    for lesson in lessons:
        app.logger.info(
            "init trial lesson:{} ,is trail:{}".format(
                lesson.lesson_id, lesson.is_final()
            )
        )
        attend = AICourseLessonAttend.query.filter(
            AICourseLessonAttend.user_id == user_id,
            AICourseLessonAttend.lesson_id == lesson.lesson_id,
        ).first()
        if attend:
            if lesson.is_final():
                item = AICourseLessonAttendDTO(
                    attend.attend_id,
                    attend.lesson_id,
                    attend.course_id,
                    attend.user_id,
                    attend.status,
                    lesson.lesson_index,
                )
                response.append(item)
            continue
        attend = AICourseLessonAttend()
        attend.attend_id = str(get_uuid(app))
        attend.course_id = course_id
        attend.lesson_id = lesson.lesson_id
        attend.user_id = user_id
        if lesson.lesson_no in ["00", "0001"]:
            attend.status = ATTEND_STATUS_NOT_STARTED
        else:
            attend.status = ATTEND_STATUS_LOCKED

        db.session.add(attend)
        if lesson.is_final() and attend.status == ATTEND_STATUS_NOT_STARTED:
            response.append(
                AICourseLessonAttendDTO(
                    attend.attend_id,
                    attend.lesson_id,
                    attend.course_id,
                    attend.user_id,
                    attend.status,
                    lesson.lesson_index,
                )
            )
        db.session.commit()
    return response


def query_raw_buy_record(app: Flask, user_id, course_id) -> AICourseBuyRecord:
    with app.app_context():
        buy_record = AICourseBuyRecord.query.filter(
            AICourseBuyRecord.course_id == course_id,
            AICourseBuyRecord.user_id == user_id,
        ).first()
        if buy_record:
            return buy_record
        return None


def query_buy_record(app: Flask, record_id: str) -> AICourseBuyRecordDTO:
    with app.app_context():
        app.logger.info('query buy record:"{}"'.format(record_id))
        buy_record = AICourseBuyRecord.query.filter(
            AICourseBuyRecord.record_id == record_id
        ).first()
        if buy_record:
            item = []
            item.append(PayItemDto("商品", "基础价格", buy_record.price, False, None))
            if buy_record.discount_value > 0:
                aitive_records = query_active_record(app, record_id)
                if aitive_records:
                    for active_record in aitive_records:
                        item.append(
                            PayItemDto(
                                "活动",
                                active_record.active_name,
                                active_record.price,
                                True,
                                None,
                            )
                        )

                discount_records = query_discount_record(app, record_id)
                if discount_records:
                    for discount_record in discount_records:
                        item.append(
                            PayItemDto(
                                "优惠",
                                discount_record.discount_name,
                                discount_record.discount_value,
                                True,
                                discount_record.discount_code,
                            )
                        )
            return AICourseBuyRecordDTO(
                buy_record.record_id,
                buy_record.user_id,
                buy_record.course_id,
                buy_record.price,
                buy_record.status,
                buy_record.discount_value,
                item,
            )
        raise_error("ORDER.ORDER_NOT_FOUND")


def fix_attend_info(app: Flask, user_id: str, course_id: str):
    with app.app_context():
        app.logger.info(
            "fix attend info for user:{} course:{}".format(user_id, course_id)
        )
        lessons = AILesson.query.filter(
            AILesson.course_id == course_id,
            AILesson.status == 1,
            AILesson.lesson_type != LESSON_TYPE_TRIAL,
        ).all()
        fix_lessons = []
        for lesson in lessons:
            attend = AICourseLessonAttend.query.filter(
                AICourseLessonAttend.user_id == user_id,
                AICourseLessonAttend.lesson_id == lesson.lesson_id,
            ).first()
            if attend:
                continue
            attend = AICourseLessonAttend()
            attend.attend_id = str(get_uuid(app))
            attend.course_id = course_id
            attend.lesson_id = lesson.lesson_id
            attend.user_id = user_id
            if lesson.lesson_no in ["01", "0101"]:
                attend.status = ATTEND_STATUS_NOT_STARTED
            else:
                attend.status = ATTEND_STATUS_LOCKED
            fix_lessons.append(
                AICourseLessonAttendDTO(
                    attend.attend_id,
                    attend.lesson_id,
                    attend.course_id,
                    attend.user_id,
                    attend.status,
                    lesson.lesson_index,
                )
            )
            db.session.add(attend)
        db.session.commit()
        return fix_lessons
