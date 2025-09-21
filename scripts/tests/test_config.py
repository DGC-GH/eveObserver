"""Tests for config.py module."""
import os
import pytest
from unittest.mock import patch
from config import (
    ESI_BASE_URL, ESI_TIMEOUT, ESI_MAX_WORKERS, WP_BASE_URL,
    WP_USERNAME, WP_APP_PASSWORD, WP_PER_PAGE, ALLOWED_CORPORATIONS,
    LOG_LEVEL, LOG_FILE, EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT,
    EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO
)


class TestConfig:
    """Test configuration loading and validation."""

    @patch.dict(os.environ, {
        'WP_URL': 'https://test.com',
        'WP_USERNAME': 'test_user',
        'WP_APP_PASSWORD': 'test_password'
    })
    def test_required_config_from_env(self):
        """Test that required config values are loaded from environment."""
        # Reload config module to pick up new env vars
        import importlib
        import config
        importlib.reload(config)

        assert config.WP_BASE_URL == 'https://test.com'
        assert config.WP_USERNAME == 'test_user'
        assert config.WP_APP_PASSWORD == 'test_password'

    def test_default_values(self):
        """Test that default values are set correctly."""
        assert ESI_BASE_URL == 'https://esi.evetech.net/latest'
        assert ESI_TIMEOUT == 30
        assert ESI_MAX_WORKERS == 10
        assert WP_PER_PAGE == 100
        assert LOG_LEVEL == 'INFO'
        assert LOG_FILE == 'eve_observer.log'
        assert ALLOWED_CORPORATIONS == ['no mercy incorporated']

    @patch.dict(os.environ, {
        'ESI_TIMEOUT': '60',
        'ESI_MAX_WORKERS': '20',
        'LOG_LEVEL': 'DEBUG'
    })
    def test_optional_config_from_env(self):
        """Test that optional config values are loaded from environment."""
        import importlib
        import config
        importlib.reload(config)

        assert config.ESI_TIMEOUT == 60
        assert config.ESI_MAX_WORKERS == 20
        assert config.LOG_LEVEL == 'DEBUG'