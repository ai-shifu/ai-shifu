"""
Unit tests for config service functions.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from flaskr.service.config.funcs import (
    _get_fernet_key,
    _get_fernet,
    _encrypt_config,
    _decrypt_config,
    _get_config_cache_key,
    _get_config_lock_key,
    get_config,
    add_config,
    update_config,
    ConfigCache,
)


class TestFernetKeyGeneration:
    """Test Fernet key generation functions."""

    def test_get_fernet_key_with_valid_secret_key(self, app):
        """Test generating Fernet key from valid SECRET_KEY."""
        with app.app_context():
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            key = _get_fernet_key(app)
            assert key is not None
            assert isinstance(key, bytes)
            assert len(key) == 44  # Base64 encoded 32-byte key

    def test_get_fernet_key_with_missing_secret_key(self, app):
        """Test that missing SECRET_KEY raises ValueError."""
        with app.app_context():
            # Save original SECRET_KEY if exists
            original_secret_key = app.config.pop("SECRET_KEY", None)
            try:
                # Ensure SECRET_KEY is not in config or is empty
                app.config["SECRET_KEY"] = ""
                with pytest.raises(ValueError, match="SECRET_KEY is not configured"):
                    _get_fernet_key(app)
            finally:
                # Restore original SECRET_KEY
                if original_secret_key:
                    app.config["SECRET_KEY"] = original_secret_key

    def test_get_fernet_key_with_empty_secret_key(self, app):
        """Test that empty SECRET_KEY raises ValueError."""
        with app.app_context():
            app.config["SECRET_KEY"] = ""
            with pytest.raises(ValueError, match="SECRET_KEY is not configured"):
                _get_fernet_key(app)

    def test_get_fernet_returns_fernet_instance(self, app):
        """Test that _get_fernet returns a Fernet instance."""
        with app.app_context():
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            fernet = _get_fernet(app)
            assert fernet is not None
            # Fernet instance should have encrypt and decrypt methods
            assert hasattr(fernet, "encrypt")
            assert hasattr(fernet, "decrypt")


class TestEncryptionDecryption:
    """Test encryption and decryption functions."""

    def test_encrypt_config_encrypts_value(self, app):
        """Test that _encrypt_config encrypts plain text value."""
        with app.app_context():
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            plain_value = "sensitive-data-123"
            encrypted = _encrypt_config(app, plain_value)
            assert encrypted is not None
            assert isinstance(encrypted, str)
            assert encrypted != plain_value
            assert len(encrypted) > 0

    def test_decrypt_config_decrypts_value(self, app):
        """Test that _decrypt_config decrypts encrypted value."""
        with app.app_context():
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            plain_value = "sensitive-data-123"
            encrypted = _encrypt_config(app, plain_value)
            decrypted = _decrypt_config(app, encrypted)
            assert decrypted == plain_value

    def test_encrypt_decrypt_roundtrip(self, app):
        """Test that encrypt-decrypt roundtrip preserves original value."""
        with app.app_context():
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            test_values = [
                "simple",
                "value with spaces",
                "value-with-special-chars!@#$%",
                "multiline\nvalue\nwith\nnewlines",
                "unicode-测试-中文",
            ]
            for value in test_values:
                encrypted = _encrypt_config(app, value)
                decrypted = _decrypt_config(app, encrypted)
                assert decrypted == value

    def test_decrypt_config_with_invalid_token(self, app):
        """Test that _decrypt_config raises ValueError for invalid token."""
        with app.app_context():
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            with pytest.raises(ValueError, match="Failed to decrypt config value"):
                _decrypt_config(app, "invalid-encrypted-token")

    def test_decrypt_config_with_different_secret_key(self, app):
        """Test that decryption fails with different SECRET_KEY."""
        with app.app_context():
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            plain_value = "sensitive-data-123"
            encrypted = _encrypt_config(app, plain_value)

            # Change SECRET_KEY
            app.config["SECRET_KEY"] = "different-secret-key-67890"
            with pytest.raises(ValueError, match="Failed to decrypt config value"):
                _decrypt_config(app, encrypted)


class TestCacheKeyGeneration:
    """Test cache and lock key generation functions."""

    def test_get_config_cache_key(self, app):
        """Test that cache key is generated correctly."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            key = _get_config_cache_key(app, "test_key")
            assert key == "test:sys:config:test_key"

    def test_get_config_lock_key(self, app):
        """Test that lock key is generated correctly."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            key = _get_config_lock_key(app, "test_key")
            assert key == "test:sys:config:lock:test_key"


class TestGetConfig:
    """Test get_config function."""

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    def test_get_config_from_environment(
        self, mock_redis, mock_get_config_from_common, app
    ):
        """Test that get_config returns value from environment first."""
        with app.app_context():
            mock_get_config_from_common.return_value = "env-value"
            result = get_config("test_key")
            assert result == "env-value"
            mock_get_config_from_common.assert_called_once_with("test_key", None)
            mock_redis.get.assert_not_called()

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs._decrypt_config")
    def test_get_config_from_cache_plain(
        self, mock_decrypt, mock_redis, mock_get_config_from_common, app
    ):
        """Test that get_config returns plain value from cache."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            cache_data = ConfigCache(
                is_encrypted=False, value="cached-value"
            ).model_dump_json()
            mock_redis.get.return_value = cache_data
            result = get_config("test_key")
            assert result == "cached-value"
            mock_decrypt.assert_not_called()

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs._decrypt_config")
    def test_get_config_from_cache_encrypted(
        self, mock_decrypt, mock_redis, mock_get_config_from_common, app
    ):
        """Test that get_config decrypts encrypted value from cache."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            mock_get_config_from_common.return_value = None
            cache_data = ConfigCache(
                is_encrypted=True, value="encrypted-value"
            ).model_dump_json()
            mock_redis.get.return_value = cache_data
            mock_decrypt.return_value = "decrypted-value"
            result = get_config("test_key")
            assert result == "decrypted-value"
            mock_decrypt.assert_called_once_with(app, "encrypted-value")

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.Config")
    @patch("flaskr.service.config.funcs._decrypt_config")
    def test_get_config_from_database_plain(
        self,
        mock_decrypt,
        mock_config_class,
        mock_redis,
        mock_get_config_from_common,
        app,
    ):
        """Test that get_config returns plain value from database."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None
            mock_lock = MagicMock()
            mock_lock.acquire.return_value = True
            mock_redis.lock.return_value = mock_lock

            # Mock database query
            mock_config_instance = MagicMock()
            mock_config_instance.value = "db-value"
            mock_config_instance.is_encrypted = 0
            mock_config_instance.created_at = datetime.now()
            mock_query = MagicMock()
            mock_query.filter.return_value.order_by.return_value.first.return_value = (
                mock_config_instance
            )
            mock_config_class.query = mock_query

            result = get_config("test_key")
            assert result == "db-value"
            mock_decrypt.assert_not_called()
            mock_lock.release.assert_called_once()

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.Config")
    @patch("flaskr.service.config.funcs._decrypt_config")
    def test_get_config_from_database_encrypted(
        self,
        mock_decrypt,
        mock_config_class,
        mock_redis,
        mock_get_config_from_common,
        app,
    ):
        """Test that get_config decrypts encrypted value from database."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None
            mock_lock = MagicMock()
            mock_lock.acquire.return_value = True
            mock_redis.lock.return_value = mock_lock

            # Mock database query
            mock_config_instance = MagicMock()
            mock_config_instance.value = "encrypted-db-value"
            mock_config_instance.is_encrypted = 1
            mock_config_instance.created_at = datetime.now()
            mock_query = MagicMock()
            mock_query.filter.return_value.order_by.return_value.first.return_value = (
                mock_config_instance
            )
            mock_config_class.query = mock_query

            mock_decrypt.return_value = "decrypted-db-value"
            result = get_config("test_key")
            assert result == "decrypted-db-value"
            mock_decrypt.assert_called_once_with(app, "encrypted-db-value")
            mock_lock.release.assert_called_once()

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.Config")
    def test_get_config_not_found(
        self, mock_config_class, mock_redis, mock_get_config_from_common, app
    ):
        """Test that get_config returns None when config not found."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None
            mock_lock = MagicMock()
            mock_lock.acquire.return_value = True
            mock_redis.lock.return_value = mock_lock

            # Mock database query returning None
            mock_query = MagicMock()
            mock_query.filter.return_value.order_by.return_value.first.return_value = (
                None
            )
            mock_config_class.query = mock_query

            result = get_config("non_existent_key")
            assert result is None
            # release may be called multiple times due to finally block
            assert mock_lock.release.call_count >= 1

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    def test_get_config_lock_failed(self, mock_redis, mock_get_config_from_common, app):
        """Test that get_config returns None when lock acquisition fails."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None
            mock_lock = MagicMock()
            mock_lock.acquire.return_value = False
            mock_redis.lock.return_value = mock_lock

            result = get_config("test_key")
            assert result is None

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.Config")
    def test_get_config_uses_env_when_db_not_ready(
        self, mock_config_class, mock_redis, mock_get_config_from_common, app
    ):
        """Fallback to environment config when database table is missing."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.side_effect = [None, "env-fallback"]
            mock_redis.get.return_value = None
            mock_lock = MagicMock()
            mock_lock.acquire.return_value = True
            mock_redis.lock.return_value = mock_lock

            mock_query = MagicMock()
            mock_query.filter.return_value.order_by.return_value.first.side_effect = (
                SQLAlchemyError("sys_configs missing")
            )
            mock_config_class.query = mock_query

            result = get_config("test_key")
            assert result == "env-fallback"
            assert mock_get_config_from_common.call_count == 2
            mock_lock.release.assert_called_once()


class TestAddConfig:
    """Test add_config function."""

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.db")
    @patch("flaskr.service.config.funcs.generate_id")
    @patch("flaskr.service.config.funcs._encrypt_config")
    @patch("flaskr.service.config.funcs.Config")
    def test_add_config_plain_value(
        self,
        mock_config_class,
        mock_encrypt,
        mock_generate_id,
        mock_db,
        mock_redis,
        mock_get_config_from_common,
        app,
    ):
        """Test adding plain text config."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None
            mock_generate_id.return_value = "test-config-bid-123"
            mock_encrypt.assert_not_called()
            mock_config_instance = MagicMock()
            mock_config_class.return_value = mock_config_instance

            result = add_config(
                app, "test_key", "test_value", is_secret=False, remark="test remark"
            )
            assert result is True
            mock_config_class.assert_called_once()
            mock_db.session.add.assert_called_once()
            mock_db.session.commit.assert_called_once()
            mock_redis.set.assert_called_once()

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.db")
    @patch("flaskr.service.config.funcs.generate_id")
    @patch("flaskr.service.config.funcs._encrypt_config")
    @patch("flaskr.service.config.funcs.Config")
    def test_add_config_encrypted_value(
        self,
        mock_config_class,
        mock_encrypt,
        mock_generate_id,
        mock_db,
        mock_redis,
        mock_get_config_from_common,
        app,
    ):
        """Test adding encrypted config."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None
            mock_generate_id.return_value = "test-config-bid-123"
            mock_encrypt.return_value = "encrypted-value"
            mock_config_instance = MagicMock()
            mock_config_class.return_value = mock_config_instance

            result = add_config(
                app, "test_key", "plain_value", is_secret=True, remark="secret remark"
            )
            assert result is True
            mock_encrypt.assert_called_once_with(app, "plain_value")
            mock_config_class.assert_called_once()
            mock_db.session.add.assert_called_once()
            mock_db.session.commit.assert_called_once()

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.db")
    @patch("flaskr.service.config.funcs.generate_id")
    @patch("flaskr.service.config.funcs._decrypt_config")
    @patch("flaskr.service.config.funcs._encrypt_config")
    @patch("flaskr.service.config.funcs.Config")
    def test_add_config_from_cache_encrypted(
        self,
        mock_config_class,
        mock_encrypt,
        mock_decrypt,
        mock_generate_id,
        mock_db,
        mock_redis,
        mock_get_config_from_common,
        app,
    ):
        """Test that add_config uses cached encrypted value if exists."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            mock_get_config_from_common.return_value = None
            cache_data = ConfigCache(
                is_encrypted=True, value="cached-encrypted"
            ).model_dump_json()
            mock_redis.get.return_value = cache_data
            mock_decrypt.return_value = "cached-decrypted"
            mock_generate_id.return_value = "test-config-bid-123"
            mock_encrypt.return_value = "re-encrypted-value"
            mock_config_instance = MagicMock()
            mock_config_class.return_value = mock_config_instance

            result = add_config(app, "test_key", "new_value", is_secret=True)
            # Should use cached decrypted value instead of new_value
            mock_decrypt.assert_called_once_with(app, "cached-encrypted")
            # Should encrypt the cached value
            mock_encrypt.assert_called_once_with(app, "cached-decrypted")
            assert result is True

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.db")
    @patch("flaskr.service.config.funcs.generate_id")
    @patch("flaskr.service.config.funcs._encrypt_config")
    @patch("flaskr.service.config.funcs.Config")
    def test_add_config_from_cache_plain(
        self,
        mock_config_class,
        mock_encrypt,
        mock_generate_id,
        mock_db,
        mock_redis,
        mock_get_config_from_common,
        app,
    ):
        """Test that add_config uses cached plain value if exists."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            cache_data = ConfigCache(
                is_encrypted=False, value="cached-plain-value"
            ).model_dump_json()
            mock_redis.get.return_value = cache_data
            mock_generate_id.return_value = "test-config-bid-123"
            mock_config_instance = MagicMock()
            mock_config_class.return_value = mock_config_instance

            result = add_config(app, "test_key", "new_value", is_secret=False)
            # Should use cached value instead of new_value
            mock_encrypt.assert_not_called()
            assert result is True

    @patch("flaskr.service.config.funcs.get_config_from_common")
    def test_add_config_skips_if_env_exists(self, mock_get_config_from_common, app):
        """Test that add_config skips if environment config exists."""
        with app.app_context():
            mock_get_config_from_common.return_value = "env-value"
            result = add_config(app, "test_key", "test_value")
            assert result is None

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    def test_add_config_returns_false_if_no_value(
        self, mock_redis, mock_get_config_from_common, app
    ):
        """Test that add_config returns False if value is empty."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None
            result = add_config(app, "test_key", "", is_secret=False)
            assert result is False


class TestUpdateConfig:
    """Test update_config function."""

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.db")
    @patch("flaskr.service.config.funcs.Config")
    @patch("flaskr.service.config.funcs._encrypt_config")
    def test_update_config_plain_value(
        self,
        mock_encrypt,
        mock_config_class,
        mock_db,
        mock_redis,
        mock_get_config_from_common,
        app,
    ):
        """Test updating plain text config."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None

            # Mock database query
            mock_config_instance = MagicMock()
            mock_config_instance.value = "old-value"
            mock_config_instance.is_secret = False
            mock_config_instance.remark = "old remark"
            mock_config_instance.created_at = datetime.now()
            mock_query = MagicMock()
            mock_query.filter.return_value.order_by.return_value.first.return_value = (
                mock_config_instance
            )
            mock_config_class.query = mock_query

            result = update_config(
                app, "test_key", "new_value", is_secret=False, remark="new remark"
            )
            assert result is True
            assert mock_config_instance.value == "new_value"
            assert (
                mock_config_instance.is_secret is False
            )  # Note: funcs.py uses is_secret but model has is_encrypted
            assert mock_config_instance.remark == "new remark"
            assert mock_config_instance.updated_by == "system"
            mock_db.session.commit.assert_called_once()
            mock_encrypt.assert_not_called()

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.db")
    @patch("flaskr.service.config.funcs.Config")
    @patch("flaskr.service.config.funcs._encrypt_config")
    def test_update_config_encrypted_value(
        self,
        mock_encrypt,
        mock_config_class,
        mock_db,
        mock_redis,
        mock_get_config_from_common,
        app,
    ):
        """Test updating encrypted config."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None
            mock_encrypt.return_value = "encrypted-new-value"

            # Mock database query
            mock_config_instance = MagicMock()
            mock_config_instance.value = "old-encrypted-value"
            mock_config_instance.is_secret = False
            mock_config_instance.remark = "old remark"
            mock_config_instance.created_at = datetime.now()
            mock_query = MagicMock()
            mock_query.filter.return_value.order_by.return_value.first.return_value = (
                mock_config_instance
            )
            mock_config_class.query = mock_query

            result = update_config(
                app, "test_key", "new_plain_value", is_secret=True, remark="new remark"
            )
            assert result is True
            assert mock_config_instance.value == "encrypted-new-value"
            assert mock_config_instance.is_secret is True
            assert mock_config_instance.remark == "new remark"
            mock_encrypt.assert_called_once_with(app, "new_plain_value")

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.db")
    @patch("flaskr.service.config.funcs.Config")
    @patch("flaskr.service.config.funcs._decrypt_config")
    @patch("flaskr.service.config.funcs._encrypt_config")
    def test_update_config_from_cache_encrypted(
        self,
        mock_encrypt,
        mock_decrypt,
        mock_config,
        mock_db,
        mock_redis,
        mock_get_config_from_common,
        app,
    ):
        """Test that update_config uses cached encrypted value if exists."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            app.config["SECRET_KEY"] = "test-secret-key-12345"
            mock_get_config_from_common.return_value = None
            cache_data = ConfigCache(
                is_encrypted=True, value="cached-encrypted"
            ).model_dump_json()
            mock_redis.get.return_value = cache_data
            mock_decrypt.return_value = "cached-decrypted"
            mock_encrypt.return_value = "re-encrypted-value"

            # Mock database query
            mock_config = MagicMock()
            mock_config.value = "old-value"
            mock_config.is_secret = False
            mock_config.remark = ""
            mock_config.created_at = datetime.now()
            mock_query = MagicMock()
            mock_query.filter.return_value.order_by.return_value.first.return_value = (
                mock_config
            )
            mock_config.query = mock_query

            result = update_config(app, "test_key", "new_value", is_secret=True)
            # Should use cached decrypted value instead of new_value
            mock_decrypt.assert_called_once_with(app, "cached-encrypted")
            # Should encrypt the cached value
            mock_encrypt.assert_called_once_with(app, "cached-decrypted")
            assert result is True

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.db")
    @patch("flaskr.service.config.funcs.Config")
    @patch("flaskr.service.config.funcs._encrypt_config")
    def test_update_config_from_cache_plain(
        self,
        mock_encrypt,
        mock_config,
        mock_db,
        mock_redis,
        mock_get_config_from_common,
        app,
    ):
        """Test that update_config uses cached plain value if exists."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            cache_data = ConfigCache(
                is_encrypted=False, value="cached-plain-value"
            ).model_dump_json()
            mock_redis.get.return_value = cache_data

            # Mock database query
            mock_config = MagicMock()
            mock_config.value = "old-value"
            mock_config.is_secret = False
            mock_config.remark = ""
            mock_config.created_at = datetime.now()
            mock_query = MagicMock()
            mock_query.filter.return_value.order_by.return_value.first.return_value = (
                mock_config
            )
            mock_config.query = mock_query

            result = update_config(app, "test_key", "new_value", is_secret=False)
            # Should use cached value instead of new_value
            mock_encrypt.assert_not_called()
            assert result is True

    @patch("flaskr.service.config.funcs.get_config_from_common")
    def test_update_config_skips_if_env_exists(self, mock_get_config_from_common, app):
        """Test that update_config returns False if environment config exists."""
        with app.app_context():
            mock_get_config_from_common.return_value = "env-value"
            result = update_config(app, "test_key", "new_value")
            assert result is False

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    @patch("flaskr.service.config.funcs.Config")
    def test_update_config_not_found(
        self, mock_config_class, mock_redis, mock_get_config_from_common, app
    ):
        """Test that update_config returns False when config not found."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None

            # Mock database query returning None
            mock_query = MagicMock()
            mock_query.filter.return_value.order_by.return_value.first.return_value = (
                None
            )
            mock_config_class.query = mock_query

            result = update_config(app, "non_existent_key", "new_value")
            assert result is False

    @patch("flaskr.service.config.funcs.get_config_from_common")
    @patch("flaskr.service.config.funcs.redis")
    def test_update_config_returns_false_if_no_value(
        self, mock_redis, mock_get_config_from_common, app
    ):
        """Test that update_config returns False if value is empty."""
        with app.app_context():
            app.config["REDIS_KEY_PREFIX"] = "test:"
            mock_get_config_from_common.return_value = None
            mock_redis.get.return_value = None
            result = update_config(app, "test_key", "", is_secret=False)
            assert result is False


class TestConfigCache:
    """Test ConfigCache model."""

    def test_config_cache_defaults(self):
        """Test ConfigCache default values."""
        cache = ConfigCache()
        assert cache.is_encrypted is False
        assert cache.value == ""

    def test_config_cache_with_values(self):
        """Test ConfigCache with explicit values."""
        cache = ConfigCache(is_encrypted=True, value="test-value")
        assert cache.is_encrypted is True
        assert cache.value == "test-value"

    def test_config_cache_serialization(self):
        """Test ConfigCache JSON serialization."""
        cache = ConfigCache(is_encrypted=True, value="test-value")
        json_str = cache.model_dump_json()
        assert isinstance(json_str, str)
        assert "test-value" in json_str

    def test_config_cache_deserialization(self):
        """Test ConfigCache JSON deserialization."""
        json_str = '{"is_encrypted": true, "value": "test-value"}'
        cache = ConfigCache.model_validate_json(json_str)
        assert cache.is_encrypted is True
        assert cache.value == "test-value"
