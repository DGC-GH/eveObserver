"""Pytest configuration and fixtures."""
import warnings

import pytest

# Suppress urllib3 NotOpenSSLWarning
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL", category=Warning)


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
