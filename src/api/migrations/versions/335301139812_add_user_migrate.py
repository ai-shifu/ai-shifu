"""Migrate legacy user data into user_users and user_auth_credentials."""

import json
import uuid
from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "335301139812"
down_revision = "6abcf5af2758"
branch_labels = None
depends_on = None

CHUNK_SIZE = 500
PROGRESS_TABLE_NAME = "tmp_user_migrate_progress"

USER_STATE_MAPPING = {
    0: 1101,
    1: 1102,
    2: 1103,
    3: 1104,
    "0": 1101,
    "1": 1102,
    "2": 1103,
    "3": 1104,
    1101: 1101,
    1102: 1102,
    1103: 1103,
    1104: 1104,
}


def _normalize_state(raw_state):
    if raw_state in USER_STATE_MAPPING:
        return USER_STATE_MAPPING[raw_state]
    try:
        key = int(str(raw_state).strip())
        if key in USER_STATE_MAPPING:
            return USER_STATE_MAPPING[key]
    except (TypeError, ValueError):
        pass
    return 1101


def _normalize_birthday(raw):
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            parts = [int(part) for part in raw.replace("/", "-").split("-")]
            if len(parts) == 3:
                return date(parts[0], parts[1], parts[2])
        except Exception:
            return date(2000, 1, 1)
    return date(2000, 1, 1)


def upgrade():
    bind = op.get_bind()
    engine = bind.engine
    metadata = sa.MetaData()

    if bind.dialect.name == "mysql":
        create_progress_sql = f"""
            CREATE TABLE IF NOT EXISTS {PROGRESS_TABLE_NAME} (
                id INT PRIMARY KEY,
                last_legacy_id BIGINT NULL,
                processed_count BIGINT NOT NULL DEFAULT 0,
                updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB
        """
    else:
        create_progress_sql = f"""
            CREATE TABLE IF NOT EXISTS {PROGRESS_TABLE_NAME} (
                id INTEGER PRIMARY KEY,
                last_legacy_id BIGINT,
                processed_count BIGINT NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """

    with engine.begin() as connection:
        connection.execute(sa.text(create_progress_sql))

    progress_table = sa.Table(
        PROGRESS_TABLE_NAME,
        metadata,
        autoload_with=engine,
    )

    with engine.begin() as connection:
        progress_row = connection.execute(sa.select(progress_table)).first()
        if not progress_row:
            connection.execute(progress_table.insert().values(id=1, processed_count=0))
            progress_row = connection.execute(sa.select(progress_table)).first()

    last_legacy_id = progress_row._mapping.get("last_legacy_id") or 0
    try:
        last_legacy_id = int(last_legacy_id)
    except (TypeError, ValueError):
        last_legacy_id = 0
    processed_total = int(progress_row._mapping.get("processed_count") or 0)

    user_info = sa.Table("user_info", metadata, autoload_with=engine)
    user_users = sa.Table("user_users", metadata, autoload_with=engine)
    user_auth = sa.Table("user_auth_credentials", metadata, autoload_with=engine)

    def upsert_user(connection, user_bid: str, payload: dict):
        existing = connection.execute(
            sa.select(user_users.c.user_bid).where(user_users.c.user_bid == user_bid)
        ).first()
        if existing:
            update_payload = payload.copy()
            update_payload.pop("user_bid", None)
            update_payload.pop("created_at", None)
            connection.execute(
                user_users.update()
                .where(user_users.c.user_bid == user_bid)
                .values(**update_payload)
            )
        else:
            connection.execute(user_users.insert().values(**payload))

    def upsert_credential(
        connection, user_bid: str, provider_name: str, identifier: str, payload: dict
    ):
        identifier_str = str(identifier)
        if provider_name in {"email", "phone"}:
            identifier_norm = identifier_str.lower()
        else:
            identifier_norm = identifier_str
        existing = connection.execute(
            sa.select(user_auth.c.id).where(
                sa.and_(
                    user_auth.c.user_bid == user_bid,
                    user_auth.c.provider_name == provider_name,
                    user_auth.c.identifier == identifier_norm,
                )
            )
        ).first()
        payload_with_meta = {
            **payload,
            "user_bid": user_bid,
            "provider_name": provider_name,
            "identifier": identifier_norm,
        }
        if existing:
            existing_id = existing._mapping["id"]
            update_payload = payload_with_meta.copy()
            update_payload.pop("created_at", None)
            update_payload.pop("credential_bid", None)
            connection.execute(
                user_auth.update()
                .where(user_auth.c.id == existing_id)
                .values(**update_payload)
            )
        else:
            connection.execute(user_auth.insert().values(**payload_with_meta))

    while True:
        with engine.connect() as read_conn:
            legacy_rows = (
                read_conn.execute(
                    sa.select(user_info)
                    .where(user_info.c.id > last_legacy_id)
                    .order_by(user_info.c.id)
                    .limit(CHUNK_SIZE)
                )
                .mappings()
                .all()
            )

        if not legacy_rows:
            break

        with engine.begin() as write_conn:
            for record in legacy_rows:
                user_bid = record.get("user_id") or uuid.uuid4().hex

                nickname = (
                    record.get("username")
                    or record.get("name")
                    or record.get("email")
                    or record.get("mobile")
                    or user_bid
                )
                birthday = _normalize_birthday(record.get("user_birth"))
                language = record.get("user_language") or ""
                state = _normalize_state(record.get("user_state"))

                raw_email = (record.get("email") or "").strip()
                email = raw_email.lower()
                mobile = (record.get("mobile") or "").strip()
                identify = email or (mobile if mobile else user_bid)

                created_at = record.get("created") or record.get("updated")
                if not created_at:
                    created_at = sa.func.now()
                updated_at = record.get("updated") or record.get("created")
                if not updated_at:
                    updated_at = sa.func.now()

                user_payload = {
                    "user_bid": user_bid,
                    "user_identify": identify,
                    "nickname": nickname,
                    "avatar": record.get("user_avatar") or "",
                    "birthday": birthday,
                    "language": language,
                    "state": state,
                    "deleted": 0,
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
                upsert_user(write_conn, user_bid, user_payload)

                verified = state in (1102, 1103, 1104)

                def credential_payload(
                    subject_id: str, subject_format: str, raw_profile: dict
                ):
                    cred_created_at = record.get("created") or record.get("updated")
                    if not cred_created_at:
                        cred_created_at = sa.func.now()
                    cred_updated_at = record.get("updated") or record.get("created")
                    if not cred_updated_at:
                        cred_updated_at = sa.func.now()
                    return {
                        "credential_bid": uuid.uuid4().hex[:32],
                        "subject_id": str(subject_id),
                        "subject_format": subject_format,
                        "raw_profile": json.dumps(raw_profile, ensure_ascii=False),
                        "state": 1202 if verified else 1201,
                        "deleted": 0,
                        "created_at": cred_created_at,
                        "updated_at": cred_updated_at,
                    }

                if mobile:
                    payload = credential_payload(mobile, "phone", {"type": "phone"})
                    upsert_credential(write_conn, user_bid, "phone", mobile, payload)

                if email:
                    payload = credential_payload(email, "email", {"type": "email"})
                    upsert_credential(write_conn, user_bid, "email", email, payload)

                open_id = record.get("user_open_id")
                if open_id:
                    payload = credential_payload(
                        open_id, "open_id", {"type": "wechat", "source": "open_id"}
                    )
                    upsert_credential(write_conn, user_bid, "wechat", open_id, payload)

                union_id = record.get("user_unicon_id")
                if union_id:
                    payload = credential_payload(
                        union_id, "unicon_id", {"type": "wechat", "source": "unicon_id"}
                    )
                    upsert_credential(write_conn, user_bid, "wechat", union_id, payload)

            last_legacy_id = legacy_rows[-1]["id"]
            try:
                last_legacy_id = int(last_legacy_id)
            except (TypeError, ValueError):
                last_legacy_id = 0
            processed_total += len(legacy_rows)

            write_conn.execute(
                progress_table.update()
                .where(progress_table.c.id == 1)
                .values(
                    last_legacy_id=last_legacy_id,
                    processed_count=processed_total,
                    updated_at=sa.func.now(),
                )
            )

        print(
            f"[user_migrate] processed {processed_total} legacy users (last legacy id: {last_legacy_id})"
        )

    with engine.begin() as connection:
        connection.execute(sa.text(f"DROP TABLE IF EXISTS {PROGRESS_TABLE_NAME}"))
    print(
        f"[user_migrate] migration completed for {processed_total} legacy users total"
    )


def downgrade():
    bind = op.get_bind()
    engine = bind.engine
    metadata = sa.MetaData()

    user_info = sa.Table("user_info", metadata, autoload_with=engine)
    user_users = sa.Table("user_users", metadata, autoload_with=engine)
    user_auth = sa.Table("user_auth_credentials", metadata, autoload_with=engine)

    with engine.connect() as read_conn:
        user_ids = [
            row.user_id for row in read_conn.execute(sa.select(user_info.c.user_id))
        ]

    if user_ids:
        with engine.begin() as connection:
            connection.execute(
                user_auth.delete().where(user_auth.c.user_bid.in_(user_ids))
            )
            connection.execute(
                user_users.delete().where(user_users.c.user_bid.in_(user_ids))
            )
