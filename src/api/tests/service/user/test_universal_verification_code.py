"""
Tests for UNIVERSAL_VERIFICATION_CODE optimization.

Test cases for ensuring that when UNIVERSAL_VERIFICATION_CODE is not set,
there is no universal verification code functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
import os


class TestUniversalVerificationCodeOptimization:
    """Test the optimization of UNIVERSAL_VERIFICATION_CODE usage."""

    def test_config_default_value_is_empty_string(self):
        """Test that UNIVERSAL_VERIFICATION_CODE has empty string as default."""
        from flaskr.common.config import ENV_VARS
        
        env_var = ENV_VARS["UNIVERSAL_VERIFICATION_CODE"]
        assert env_var.default == ""
        assert env_var.required is False

    def test_get_config_when_not_set(self, monkeypatch):
        """Test get_config returns empty string when UNIVERSAL_VERIFICATION_CODE is not set."""
        # Clear any existing environment variable
        monkeypatch.delenv("UNIVERSAL_VERIFICATION_CODE", raising=False)
        
        from flaskr.common.config import get_config
        value = get_config("UNIVERSAL_VERIFICATION_CODE")
        assert value == ""

    def test_get_config_when_set_to_value(self, monkeypatch):
        """Test get_config returns the value when UNIVERSAL_VERIFICATION_CODE is set."""
        test_code = "test123"
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", test_code)
        
        from flaskr.common.config import ENV_VARS, EnhancedConfig
        enhanced = EnhancedConfig(ENV_VARS)
        value = enhanced.get("UNIVERSAL_VERIFICATION_CODE")
        assert value == test_code

    def test_get_config_when_set_to_empty_string(self, monkeypatch):
        """Test get_config returns empty string when UNIVERSAL_VERIFICATION_CODE is explicitly set to empty."""
        monkeypatch.setenv("UNIVERSAL_VERIFICATION_CODE", "")
        
        from flaskr.common.config import ENV_VARS, EnhancedConfig
        enhanced = EnhancedConfig(ENV_VARS)
        value = enhanced.get("UNIVERSAL_VERIFICATION_CODE")
        assert value == ""

    def test_fix_check_code_when_not_set(self, monkeypatch):
        """Test FIX_CHECK_CODE is None when UNIVERSAL_VERIFICATION_CODE is not set."""
        # Clear any existing environment variable  
        monkeypatch.delenv("UNIVERSAL_VERIFICATION_CODE", raising=False)
        
        # Mock get_config to return empty string (simulating not set)
        with patch('flaskr.service.user.common.get_config') as mock_get_config:
            mock_get_config.return_value = ""
            
            # Reload the constant
            import flaskr.service.user.common
            import importlib
            importlib.reload(flaskr.service.user.common)
            
            from flaskr.service.user.common import FIX_CHECK_CODE
            assert FIX_CHECK_CODE is None

    def test_fix_check_code_when_set(self, monkeypatch):
        """Test FIX_CHECK_CODE has the value when UNIVERSAL_VERIFICATION_CODE is set."""
        test_code = "test123"
        
        # Mock get_config to return the test code
        with patch('flaskr.service.user.common.get_config') as mock_get_config:
            mock_get_config.return_value = test_code
            
            # Reload the constant
            import flaskr.service.user.common
            import importlib
            importlib.reload(flaskr.service.user.common)
            
            from flaskr.service.user.common import FIX_CHECK_CODE
            assert FIX_CHECK_CODE == test_code

    def test_sms_verification_logic_without_universal_code(self):
        """Test SMS verification logic when no universal code is set."""
        # Mock dependencies
        mock_app = MagicMock()
        mock_redis = MagicMock()
        
        with patch('flaskr.service.user.common.redis', mock_redis), \
             patch('flaskr.service.user.common.FIX_CHECK_CODE', None):
            
            from flaskr.service.user.common import verify_sms_code
            from flaskr.service.user.common import raise_error
            
            # Mock Redis to return None (no stored code)
            mock_redis.get.return_value = None
            
            # Test 1: Should raise error when no stored code and no universal code
            with pytest.raises(Exception):  # raise_error will throw exception
                with patch('flaskr.service.user.common.raise_error', side_effect=Exception("USER.SMS_SEND_EXPIRED")):
                    verify_sms_code(mock_app, "user123", "1234567890", "1234")
            
            # Test 2: Should validate normally when stored code exists
            mock_redis.get.return_value = b"1234"  # Redis returns bytes
            mock_redis.delete.return_value = True
            
            # Mock database and other dependencies
            with patch('flaskr.service.user.common.User') as mock_user, \
                 patch('flaskr.service.user.common.db') as mock_db, \
                 patch('flaskr.service.user.common.generate_token') as mock_token, \
                 patch('flaskr.service.user.common.get_user_profile_labels'), \
                 patch('flaskr.service.user.common.get_user_language'), \
                 patch('flaskr.service.user.common.get_user_openid'), \
                 patch('flaskr.service.user.common.init_first_course'):
                
                mock_user_instance = MagicMock()
                mock_user_instance.user_id = "user123"
                mock_user_instance.mobile = "1234567890"
                mock_user_instance.user_state = 1
                mock_user.query.filter.return_value.order_by.return_value.order_by.return_value.first.return_value = mock_user_instance
                mock_token.return_value = "test_token"
                
                # This should not raise an exception
                result = verify_sms_code(mock_app, "user123", "1234567890", "1234")
                assert result is not None

    def test_sms_verification_logic_with_universal_code(self):
        """Test SMS verification logic when universal code is set."""
        # Mock dependencies
        mock_app = MagicMock()
        mock_redis = MagicMock()
        universal_code = "999999"
        
        with patch('flaskr.service.user.common.redis', mock_redis), \
             patch('flaskr.service.user.common.FIX_CHECK_CODE', universal_code):
            
            from flaskr.service.user.common import verify_sms_code
            
            # Mock Redis to return None (no stored code)
            mock_redis.get.return_value = None
            mock_redis.delete.return_value = True
            
            # Mock database and other dependencies
            with patch('flaskr.service.user.common.User') as mock_user, \
                 patch('flaskr.service.user.common.db') as mock_db, \
                 patch('flaskr.service.user.common.generate_token') as mock_token, \
                 patch('flaskr.service.user.common.get_user_profile_labels'), \
                 patch('flaskr.service.user.common.get_user_language'), \
                 patch('flaskr.service.user.common.get_user_openid'), \
                 patch('flaskr.service.user.common.init_first_course'):
                
                mock_user_instance = MagicMock()
                mock_user_instance.user_id = "user123"
                mock_user_instance.mobile = "1234567890"
                mock_user_instance.user_state = 1
                mock_user.query.filter.return_value.order_by.return_value.order_by.return_value.first.return_value = mock_user_instance
                mock_token.return_value = "test_token"
                
                # Should succeed with universal code even when no stored code
                result = verify_sms_code(mock_app, "user123", "1234567890", universal_code)
                assert result is not None

    def test_mail_verification_logic_without_universal_code(self):
        """Test email verification logic when no universal code is set."""
        # Mock dependencies
        mock_app = MagicMock()
        mock_redis = MagicMock()
        
        with patch('flaskr.service.user.common.redis', mock_redis), \
             patch('flaskr.service.user.common.FIX_CHECK_CODE', None):
            
            from flaskr.service.user.common import verify_mail_code
            
            # Mock Redis to return None (no stored code)
            mock_redis.get.return_value = None
            
            # Test: Should raise error when no stored code and no universal code
            with pytest.raises(Exception):  # raise_error will throw exception
                with patch('flaskr.service.user.common.raise_error', side_effect=Exception("USER.MAIL_SEND_EXPIRED")):
                    verify_mail_code(mock_app, "user123", "test@example.com", "1234")

    def test_mail_verification_logic_with_universal_code(self):
        """Test email verification logic when universal code is set."""
        # Mock dependencies
        mock_app = MagicMock()
        mock_redis = MagicMock()
        universal_code = "999999"
        
        with patch('flaskr.service.user.common.redis', mock_redis), \
             patch('flaskr.service.user.common.FIX_CHECK_CODE', universal_code):
            
            from flaskr.service.user.common import verify_mail_code
            
            # Mock Redis to return None (no stored code)
            mock_redis.get.return_value = None
            mock_redis.delete.return_value = True
            
            # Mock database and other dependencies
            with patch('flaskr.service.user.common.User') as mock_user, \
                 patch('flaskr.service.user.common.db') as mock_db, \
                 patch('flaskr.service.user.common.generate_token') as mock_token, \
                 patch('flaskr.service.user.common.get_user_profile_labels'), \
                 patch('flaskr.service.user.common.get_user_language'), \
                 patch('flaskr.service.user.common.get_user_openid'), \
                 patch('flaskr.service.user.common.init_first_course'):
                
                mock_user_instance = MagicMock()
                mock_user_instance.user_id = "user123"
                mock_user_instance.email = "test@example.com"
                mock_user_instance.user_state = 1
                mock_user.query.filter.return_value.order_by.return_value.order_by.return_value.first.return_value = mock_user_instance
                mock_token.return_value = "test_token"
                
                # Should succeed with universal code even when no stored code
                result = verify_mail_code(mock_app, "user123", "test@example.com", universal_code)
                assert result is not None