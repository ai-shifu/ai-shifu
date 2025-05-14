from datetime import datetime
import pytz
from flask import Flask

from ...dao import db
from .models import Active, ActiveUserRecord
from ...util import generate_id
from ..common import raise_error
from flaskr.service.active.consts import (
    ACTIVE_JOIN_TYPE_AUTO,
    ACTIVE_JOIN_STATUS_ENABLE,
    ACTIVE_JOIN_STATUS_FAILURE,
)


def save_active(
    app,
    user_id,
    active_course,
    active_name,
    active_desc,
    active_start_time,
    active_end_time,
    active_price,
    active_status,
    active_id=None,
    **args,
):
    active_start_time = datetime.strptime(active_start_time, "%Y-%m-%d %H:%M:%S")
    active_end_time = datetime.strptime(active_end_time, "%Y-%m-%d %H:%M:%S")
    if active_end_time < active_start_time:
        raise_error("COMMON.START_TIME_NOT_ALLOWED")
    if active_id is not None and active_id != "":
        active = Active.query.filter(Active.active_id == active_id).first()
    else:
        active = Active()
    active.active_id = generate_id(app)
    active.active_name = active_name
    active.active_desc = active_desc
    active.active_status = active_status
    active.active_start_time = active_start_time
    active.active_end_time = active_end_time
    active.active_price = active_price
    active.active_filter = str({"course_id": active_course})
    active.active_course = active_course
    if args.get("active_join_type"):
        active.active_join_type = args.get("active_join_type")
    if active_id:
        db.session.merge(active)
    else:
        db.session.add(active)
    db.session.commit()
    return active.active_id


def create_active_user_record(
    app, active_id, user_id, price, order_id, status, active_name
) -> ActiveUserRecord:
    active_user_record = ActiveUserRecord()
    active_user_record.record_id = generate_id(app)
    active_user_record.active_id = active_id
    active_user_record.user_id = user_id
    active_user_record.price = price
    active_user_record.order_id = order_id
    active_user_record.status = status
    active_user_record.active_name = active_name
    db.session.add(active_user_record)
    return active_user_record


def query_to_failure_active(app, user_id, order_id):
    with app.app_context():
        ActiveUserRecord.query.filter(
            ActiveUserRecord.order_id == order_id,
            ActiveUserRecord.user_id == user_id,
            ActiveUserRecord.status == ACTIVE_JOIN_STATUS_ENABLE,
        ).update(
            {ActiveUserRecord.status: ACTIVE_JOIN_STATUS_FAILURE},
            synchronize_session="fetch",
        )
        db.session.commit()
        return ActiveUserRecord.active_id


# query active and join active
def query_and_join_active(
    app, course_id, user_id, order_id, active_id=None
) -> list[ActiveUserRecord]:
    bj_time = pytz.timezone("Asia/Shanghai")
    now = datetime.now(bj_time)
    app.logger.info(f"find active for course:{course_id} and user:{user_id},time:{now}")
    active_infos = Active.query.filter(
        Active.active_course == course_id,
        Active.active_status == 1,
        Active.active_start_time <= now,
        Active.active_end_time >= now,
        Active.active_join_type == ACTIVE_JOIN_TYPE_AUTO,
    ).all()
    if active_id:
        append_active_info = Active.query.filter(
            Active.active_id == active_id,
            Active.active_status == 1,
            Active.active_start_time <= now,
            Active.active_end_time >= now,
            Active.active_course == course_id,
        ).first()
        if append_active_info:
            app.logger.info(
                f"append active info:{append_active_info.active_name} {append_active_info.active_id}"
            )
            active_infos.append(append_active_info)
    if not active_infos:
        app.logger.info(f"no active for course:{course_id} and user:{user_id}")
        return []
    active_user_records = []
    for active_info in active_infos:
        app.logger.info(
            f"active info:{active_info.active_name} {active_info.active_id}"
        )
        active_user_record = ActiveUserRecord.query.filter(
            ActiveUserRecord.active_id == active_info.active_id,
            ActiveUserRecord.user_id == user_id,
            ActiveUserRecord.status == ACTIVE_JOIN_STATUS_ENABLE,
        ).first()
        if active_user_record:
            active_user_records.append(active_user_record)
        else:
            active_user_records.append(
                create_active_user_record(
                    app,
                    active_info.active_id,
                    user_id,
                    active_info.active_price,
                    order_id,
                    ACTIVE_JOIN_STATUS_ENABLE,
                    active_info.active_name,
                )
            )
    return active_user_records


# join active
def join_active(app, active_id, user_id, order_id):
    active_user_record = ActiveUserRecord.query.filter(
        ActiveUserRecord.active_id == active_id,
        ActiveUserRecord.user_id == user_id,
    ).first()
    if active_user_record:
        raise_error("ACTIVE.ALREADY_JOINED")
    active_info = query_active(app, active_id)
    active_user_record = create_active_user_record(
        app,
        active_id,
        user_id,
        active_info.active_price,
        order_id,
        ACTIVE_JOIN_STATUS_ENABLE,
        active_info.active_name,
    )
    return active_user_record


def query_active(app, active_id) -> Active:
    return Active.query.filter(Active.active_id == active_id).first()


def query_active_record(
    app: Flask, order_id: str, recaul_discount: bool
) -> list[ActiveUserRecord]:
    active_user_records = ActiveUserRecord.query.filter(
        ActiveUserRecord.order_id == order_id
    ).all()
    active_ids = [i.active_id for i in active_user_records]
    bj_time = pytz.timezone("Asia/Shanghai")
    if recaul_discount:
        now = datetime.now(bj_time)
        actives = Active.query.filter(
            Active.active_id.in_(active_ids),
            Active.active_status == 1,
            Active.active_start_time <= now,
            Active.active_end_time >= now,
        ).all()
    else:
        actives = Active.query.filter(
            Active.active_id.in_(active_ids),
        ).all()
    active_maps = {i.active_id: i for i in actives}

    ret = []
    for active_user_record in active_user_records:
        active = active_maps.get(active_user_record.active_id, None)
        if active:
            ret.append(active_user_record)
    return ret
