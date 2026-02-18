from flask import Flask
import hashlib
import os
from io import BytesIO
from werkzeug.datastructures import FileStorage
from flaskr.service.user.models import UserInfo
from flaskr.dao import db
from flaskr.service.shifu.models import AiCourseAuth
from flaskr.util import generate_id
from flaskr.service.config.funcs import add_config, get_config, update_config
from flaskr.common.cache_provider import cache as redis
from flaskr.service.shifu.shifu_import_export_funcs import import_shifu
from flaskr.service.shifu.shifu_publish_funcs import publish_shifu_draft

import json
from pathlib import Path
from typing import Tuple


def _calculate_hash(content: bytes) -> str:
    """Calculate SHA256 hash for the given content."""

    return hashlib.sha256(content).hexdigest()


def _upsert_config(app: Flask, key: str, value: str, remark: str) -> None:
    """Update config if it exists, otherwise add it."""

    updated = update_config(app, key, value, is_secret=False, remark=remark)
    if not updated:
        add_config(app, key, value, is_secret=False, remark=remark)


def _process_demo_shifu(
    app: Flask,
    demo_file: str,
    config_key: str,
    config_remark: str,
    hash_config_key: str,
    hash_config_remark: str,
) -> str:
    """
    Process demo shifu: skip import if file unchanged, otherwise import/update and
    upsert configs for shifu bid and file hash.

    Args:
        app: Flask application instance
        demo_file: Path to demo JSON file
        config_key: Config key (e.g., "DEMO_SHIFU_BID" or "DEMO_EN_SHIFU_BID")
        config_remark: Config remark description
        hash_config_key: Config key for file hash
        hash_config_remark: Config remark for file hash

    Returns:
        str: The shifu_bid of the processed shifu
    """
    # Read file content
    # File is in src/api/demo_shifus/ directory, command is in src/api/flaskr/command/
    current_file = Path(__file__).resolve()
    # From src/api/flaskr/command/ to src/api/: go up 2 levels (command -> flaskr -> api)
    demo_file_path = current_file.parent.parent.parent / "demo_shifus" / demo_file
    with open(demo_file_path, "rb") as f:
        file_content = f.read()

    file_hash = _calculate_hash(file_content)

    # Check if config exists
    existing_shifu_bid = get_config(config_key, None)
    existing_hash = get_config(hash_config_key, None)

    # Skip import if file unchanged and shifu already exists
    if existing_shifu_bid and existing_hash == file_hash:
        app.logger.info("Demo shifu %s unchanged, skipping import", demo_file)
        return existing_shifu_bid

    # Create FileStorage from bytes
    file_storage = FileStorage(
        stream=BytesIO(file_content),
        filename=os.path.basename(demo_file_path),
        name="file",
    )

    # Import or update shifu
    if existing_shifu_bid:
        # Update existing shifu
        shifu_bid = import_shifu(app, existing_shifu_bid, file_storage, "system")
    else:
        # Import new shifu
        shifu_bid = import_shifu(app, None, file_storage, "system")

    # Publish shifu.
    # This is a one-off console command; run summary/ask prompt generation
    # synchronously to avoid being interrupted by process exit.
    publish_shifu_draft(app, "system", shifu_bid, "", sync_summary=True)

    # Persist shifu bid and hash in configs
    _upsert_config(app, config_key, shifu_bid, config_remark)
    _upsert_config(app, hash_config_key, file_hash, hash_config_remark)

    return shifu_bid


def _ensure_creator_permissions(app: Flask, shifu_bid: str):
    """
    Ensure all creator users have at least active `view` permission for the given shifu.

    Existing auth types are preserved and augmented with `view`.

    Args:
        app: Flask application instance
        shifu_bid: Shifu business identifier
    """
    users = UserInfo.query.filter(UserInfo.is_creator == 1).all()
    user_bids = [user.user_bid for user in users]
    existing_auths = (
        AiCourseAuth.query.filter(
            AiCourseAuth.course_id == shifu_bid,
            AiCourseAuth.user_id.in_(user_bids),
        ).all()
        if user_bids
        else []
    )
    auth_map = {auth.user_id: auth for auth in existing_auths}

    changed_user_ids: set[str] = set()

    for user in users:
        auth = auth_map.get(user.user_bid)
        if not auth:
            db.session.add(
                AiCourseAuth(
                    course_auth_id=generate_id(app),
                    user_id=user.user_bid,
                    course_id=shifu_bid,
                    auth_type=json.dumps(["view"]),
                    status=1,
                )
            )
            changed_user_ids.add(user.user_bid)
            continue

        auth_values = _normalize_auth_type_values(auth.auth_type)
        if "view" not in {v.lower() for v in auth_values}:
            auth_values.add("view")
        auth.auth_type = json.dumps(sorted(auth_values))
        auth.status = 1
        changed_user_ids.add(user.user_bid)

    db.session.commit()
    _invalidate_permission_cache(app, shifu_bid, changed_user_ids)


def _normalize_auth_type_values(raw_value: object) -> set[str]:
    """Normalize stored auth_type payload to a string set."""
    if raw_value is None:
        return set()
    if isinstance(raw_value, (list, tuple, set)):
        return {str(item).strip() for item in raw_value if str(item).strip()}
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return set()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {text}
        if isinstance(parsed, (list, tuple, set)):
            return {str(item).strip() for item in parsed if str(item).strip()}
        if isinstance(parsed, str) and parsed.strip():
            return {parsed.strip()}
    return set()


def _has_view_permission(auth_values: set[str]) -> bool:
    """Check whether normalized auth values already contain explicit `view`."""
    lowered = {value.lower() for value in auth_values}
    return "view" in lowered


def _invalidate_permission_cache(
    app: Flask, shifu_bid: str, user_ids: set[str]
) -> None:
    """Invalidate shifu permission cache entries for affected users."""
    if not user_ids:
        return
    with app.app_context():
        prefix = get_config("REDIS_KEY_PREFIX")
        if not prefix:
            return
        for user_id in user_ids:
            redis.delete(f"{prefix}shifu_permission:{user_id}:{shifu_bid}")


def backfill_course_view_permissions(
    app: Flask,
    shifu_bid: str,
    only_creators: bool = False,
    dry_run: bool = True,
) -> Tuple[int, int, int]:
    """
    Backfill `view` permission for a course.

    Returns tuple: (target_user_count, inserted_count, updated_count)
    """
    if not shifu_bid:
        raise ValueError("shifu_bid is required")

    with app.app_context():
        query = UserInfo.query.filter(UserInfo.deleted == 0)
        if only_creators:
            query = query.filter(UserInfo.is_creator == 1)
        users = query.all()
        user_bids = [user.user_bid for user in users]

        existing_auths = (
            AiCourseAuth.query.filter(
                AiCourseAuth.course_id == shifu_bid,
                AiCourseAuth.user_id.in_(user_bids),
            ).all()
            if user_bids
            else []
        )
        auth_map = {auth.user_id: auth for auth in existing_auths}

        inserted = 0
        updated = 0
        changed_user_ids: set[str] = set()

        for user in users:
            auth = auth_map.get(user.user_bid)

            if not auth:
                inserted += 1
                if dry_run:
                    continue
                db.session.add(
                    AiCourseAuth(
                        course_auth_id=generate_id(app),
                        user_id=user.user_bid,
                        course_id=shifu_bid,
                        auth_type=json.dumps(["view"]),
                        status=1,
                    )
                )
                changed_user_ids.add(user.user_bid)
                continue

            auth_values = _normalize_auth_type_values(auth.auth_type)
            has_view = _has_view_permission(auth_values)
            needs_update = auth.status != 1 or not has_view
            if not needs_update:
                continue

            updated += 1
            if dry_run:
                continue

            if not has_view:
                # Keep existing auth values while ensuring view is present.
                auth_values.add("view")
            auth.auth_type = json.dumps(sorted(auth_values))
            auth.status = 1
            changed_user_ids.add(user.user_bid)

        if not dry_run:
            db.session.commit()
            _invalidate_permission_cache(app, shifu_bid, changed_user_ids)

        return len(users), inserted, updated


def update_demo_shifu(app: Flask):
    """Update demo shifu for both Chinese and English versions"""
    if os.getenv("SKIP_DEMO_SHIFU_IMPORT"):
        app.logger.info("Skip demo shifu import due to SKIP_DEMO_SHIFU_IMPORT")
        return

    with app.app_context():
        # Process Chinese demo shifu (cn_demo.json -> DEMO_SHIFU_BID)
        cn_shifu_bid = _process_demo_shifu(
            app,
            "cn_demo.json",
            "DEMO_SHIFU_BID",
            "Demo shifu business identifier (Chinese)",
            "DEMO_SHIFU_HASH",
            "Demo shifu file hash (Chinese)",
        )
        app.logger.info(f"Chinese demo shifu bid: {cn_shifu_bid}")
        _ensure_creator_permissions(app, cn_shifu_bid)

        # Process English demo shifu (en_demo.json -> DEMO_EN_SHIFU_BID)
        en_shifu_bid = _process_demo_shifu(
            app,
            "en_demo.json",
            "DEMO_EN_SHIFU_BID",
            "Demo shifu business identifier (English)",
            "DEMO_EN_SHIFU_HASH",
            "Demo shifu file hash (English)",
        )
        app.logger.info(f"English demo shifu bid: {en_shifu_bid}")
        _ensure_creator_permissions(app, en_shifu_bid)

        db.session.commit()
