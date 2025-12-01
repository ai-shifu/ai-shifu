from flask import Flask
from cryptography.fernet import Fernet
import base64
import hashlib
from flaskr.service.config.models import Config
from flaskr.common.config import get_config as get_config_from_common
from flaskr.dao import db, redis_client as redis
from flaskr.util import generate_id
from pydantic import BaseModel, Field
from flaskr.framework import extensible
import random


class ConfigCache(BaseModel):
    is_encrypted: bool = Field(default=False)
    value: str = Field(default="")


def _get_fernet_key(app: Flask) -> bytes:
    """
    Generate Fernet key from SECRET_KEY.
    Fernet requires a 32-byte key, so we hash SECRET_KEY with SHA256.
    """
    with app.app_context():
        secret_key = app.config.get("SECRET_KEY", "")
        if not secret_key:
            raise ValueError("SECRET_KEY is not configured")

        key_bytes = hashlib.sha256(secret_key.encode()).digest()
        return base64.urlsafe_b64encode(key_bytes)


def _get_fernet(app: Flask) -> Fernet:
    """
    Get Fernet instance for encryption/decryption.
    """
    key = _get_fernet_key(app)
    return Fernet(key)


def _encrypt_config(app: Flask, value: str) -> str:
    """
    Encrypt config value and store it in database.

    Args:
        app: Flask application instance
        value: Plain text value to encrypt

    Returns:
        Encrypted value as base64 string
    """
    with app.app_context():
        fernet = _get_fernet(app)
        encrypted_value = fernet.encrypt(value.encode())
        return encrypted_value.decode()


def _decrypt_config(app: Flask, encrypted_value: str) -> str:
    """
    Decrypt config value.

    Args:
        app: Flask application instance
        encrypted_value: Encrypted value as base64 string

    Returns:
        Decrypted plain text value

    Raises:
        ValueError: If decryption fails (invalid token or corrupted data)
    """
    with app.app_context():
        try:
            fernet = _get_fernet(app)
            decrypted_value = fernet.decrypt(encrypted_value.encode())
            return decrypted_value.decode()
        except Exception as e:
            raise ValueError(f"Failed to decrypt config value: {str(e)}")


def _get_config_cache_key(app: Flask, key: str) -> str:
    return app.config["REDIS_KEY_PREFIX"] + "sys:config:" + key


def _get_config_lock_key(app: Flask, key: str) -> str:
    return app.config["REDIS_KEY_PREFIX"] + "sys:config:lock:" + key


@extensible
def get_config(key: str) -> str:
    """
    Get config value by key, automatically decrypt if is_secret=1.

    Args:
        app: Flask application instance
        key: Config key

    Returns:
        Config value (decrypted if is_secret=1, plain text otherwise)
        None if config not found
    Raises:
        ValueError: If config not found or decryption fails
    """
    from flask import current_app, has_app_context

    if not has_app_context():
        return get_config_from_common(key, None)
    app = current_app
    with app.app_context():
        env_value = get_config_from_common(key, None)
        if env_value:
            return env_value
        cache_key = _get_config_cache_key(app, key)
        cache = redis.get(cache_key)
        if cache:
            cache_config = ConfigCache.model_validate_json(cache)
            if cache_config.is_encrypted:
                return _decrypt_config(app, cache_config.value)
            return cache_config.value
        lock_key = _get_config_lock_key(app, key)
        lock = redis.lock(lock_key, timeout=1, blocking_timeout=1)
        if lock.acquire(blocking=False):
            try:
                config = (
                    Config.query.filter(
                        Config.key == key,
                        Config.deleted == 0,
                    )
                    .order_by(Config.created_at.desc())
                    .first()
                )
                if not config:
                    return None
                raw_value = config.value
                if bool(config.is_encrypted):
                    value = _decrypt_config(app, raw_value)
                else:
                    value = raw_value
                redis.set(
                    cache_key,
                    ConfigCache(
                        is_encrypted=bool(config.is_encrypted),
                        value=raw_value,
                    ).model_dump_json(),
                    ex=86400 + random.randint(0, 3600),
                )
                return value
            finally:
                lock.release()
        return None


def add_config(
    app: Flask, key: str, value: str, is_secret: bool = False, remark: str = ""
) -> None:
    """
    Add config to database.
    """
    with app.app_context():
        app.logger.info(
            f"Adding config: {key}, value: {value}, is_secret: {is_secret}, remark: {remark}"
        )
        env_value = get_config_from_common(key, None)
        if env_value:
            return
        # Check if config already exists in database
        existing_config = (
            Config.query.filter(
                Config.key == key,
                Config.deleted == 0,
            )
            .order_by(Config.created_at.desc())
            .first()
        )
        if existing_config:
            # Config already exists, update it instead
            if is_secret:
                value = _encrypt_config(app, value)
            existing_config.value = value
            existing_config.is_encrypted = is_secret
            existing_config.remark = remark
            existing_config.updated_by = "system"
            db.session.commit()
            cache_key = _get_config_cache_key(app, key)
            redis.set(
                cache_key,
                ConfigCache(is_encrypted=is_secret, value=value).model_dump_json(),
                ex=86400 + random.randint(0, 3600),
            )
            return True
        # Config doesn't exist, add new one
        if value:
            if is_secret:
                value = _encrypt_config(app, value)
            config = Config(
                config_bid=generate_id(app),
                key=key,
                value=value,
                deleted=0,
                is_encrypted=is_secret,
                remark=remark,
                updated_by="",
            )
            db.session.add(config)
            db.session.commit()
            cache_key = _get_config_cache_key(app, key)
            redis.set(
                cache_key,
                ConfigCache(is_encrypted=is_secret, value=value).model_dump_json(),
                ex=86400 + random.randint(0, 3600),
            )
            return True
        return False


def update_config(
    app: Flask, key: str, value: str, is_secret: bool = False, remark: str = ""
) -> bool:
    """
    Update config in database.
    """
    with app.app_context():
        env_value = get_config_from_common(key, None)
        if env_value:
            return False
        cache_key = _get_config_cache_key(app, key)
        cache = redis.get(cache_key)
        if cache:
            cache_config = ConfigCache.model_validate_json(cache)
            if cache_config.is_encrypted:
                value = _decrypt_config(app, cache_config.value)
            else:
                value = cache_config.value
        if value:
            if is_secret:
                value = _encrypt_config(app, value)
            config = (
                Config.query.filter(
                    Config.key == key,
                    Config.deleted == 0,
                )
                .order_by(Config.created_at.desc())
                .first()
            )
            if not config:
                config = Config(
                    config_bid=generate_id(app),
                    key=key,
                    value=value,
                    deleted=0,
                    is_encrypted=is_secret,
                    remark=remark,
                    updated_by="system",
                )
                db.session.add(config)
            else:
                config.value = value
                config.is_encrypted = is_secret
                config.remark = remark
                config.updated_by = "system"
            db.session.commit()
            redis.set(
                cache_key,
                ConfigCache(is_encrypted=is_secret, value=value).model_dump_json(),
                ex=86400 + random.randint(0, 3600),
            )
            return True
        return False
