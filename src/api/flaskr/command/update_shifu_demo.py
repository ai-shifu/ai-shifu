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
from flaskr.service.shifu.shifu_import_export_funcs import import_shifu
from flaskr.service.shifu.shifu_publish_funcs import publish_shifu_draft

import json
from pathlib import Path


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
    Ensure all creator users have permissions for the given shifu.

    Args:
        app: Flask application instance
        shifu_bid: Shifu business identifier
    """
    users = UserInfo.query.filter(UserInfo.is_creator == 1).all()
    for user in users:
        auth = AiCourseAuth.query.filter(
            AiCourseAuth.user_id == user.user_bid,
            AiCourseAuth.course_id == shifu_bid,
        ).first()
        if not auth:
            auth = AiCourseAuth(
                course_auth_id=generate_id(app),
                user_id=user.user_bid,
                course_id=shifu_bid,
                auth_type=json.dumps(["view"]),
                status=1,
            )
            db.session.add(auth)
        else:
            auth.auth_type = json.dumps(["view"])
            auth.status = 1
        db.session.commit()


def update_demo_shifu(app: Flask):
    """Update demo shifu for both Chinese and English versions"""
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
