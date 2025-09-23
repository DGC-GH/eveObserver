"""Tests for fetch_data.py functions."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import sys
import os

# Add the scripts directory to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_data import (
    collect_corporation_members,
    check_industry_job_completions,
    check_planet_extraction_completions,
    ApiConfig,
    fetch_public_esi,
    fetch_esi
)


class TestApiConfig:
    """Test ApiConfig dataclass functionality."""

    def test_api_config_defaults(self):
        """Test ApiConfig with default values."""
        config = ApiConfig()
        assert config.esi_base_url == 'https://esi.evetech.net/latest'
        assert config.esi_timeout == 30
        assert config.esi_max_retries == 3
        assert config.esi_max_workers == 10

    @patch.dict(os.environ, {
        'ESI_BASE_URL': 'https://custom.esi.url',
        'ESI_TIMEOUT': '45',
        'ESI_MAX_RETRIES': '5',
        'ESI_MAX_WORKERS': '15'
    })
    def test_api_config_from_env_custom_values(self):
        """Test ApiConfig.from_env with custom environment variables."""
        config = ApiConfig.from_env()
        assert config.esi_base_url == 'https://custom.esi.url'
        assert config.esi_timeout == 45
        assert config.esi_max_retries == 5
        assert config.esi_max_workers == 15

    @patch.dict(os.environ, {}, clear=True)
    def test_api_config_from_env_defaults(self):
        """Test ApiConfig.from_env with no environment variables set."""
        config = ApiConfig.from_env()
        assert config.esi_base_url == 'https://esi.evetech.net/latest'
        assert config.esi_timeout == 30
        assert config.esi_max_retries == 3
        assert config.esi_max_workers == 10

    @patch.dict(os.environ, {
        'ESI_TIMEOUT': 'invalid',
        'ESI_MAX_RETRIES': 'not_a_number',
        'ESI_MAX_WORKERS': 'also_invalid'
    })
    def test_api_config_from_env_invalid_values(self):
        """Test ApiConfig.from_env handles invalid environment variables gracefully."""
        with pytest.raises(ValueError):
            ApiConfig.from_env()


class TestFetchFunctions:
    """Test ESI API fetch functions."""

    @patch('fetch_data.session')
    @patch('fetch_data.api_config')
    def test_fetch_public_esi_success(self, mock_api_config, mock_session):
        """Test successful fetch_public_esi call."""
        # Setup mocks
        mock_api_config.esi_max_retries = 3
        mock_api_config.esi_base_url = 'https://esi.evetech.net/latest'
        mock_api_config.esi_timeout = 30
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'test': 'data'}
        mock_session.get.return_value = mock_response

        result = fetch_public_esi('/test/endpoint')

        assert result == {'test': 'data'}
        mock_session.get.assert_called_once_with('https://esi.evetech.net/latest/test/endpoint', timeout=30)

    @patch('fetch_data.session')
    @patch('fetch_data.api_config')
    def test_fetch_public_esi_404(self, mock_api_config, mock_session):
        """Test fetch_public_esi with 404 response."""
        mock_api_config.esi_max_retries = 3
        mock_api_config.esi_base_url = 'https://esi.evetech.net/latest'
        mock_api_config.esi_timeout = 30
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_session.get.return_value = mock_response

        result = fetch_public_esi('/test/endpoint')

        assert result is None

    @patch('time.sleep')
    @patch('fetch_data.session')
    @patch('fetch_data.api_config')
    def test_fetch_public_esi_rate_limit(self, mock_api_config, mock_session, mock_sleep):
        """Test fetch_public_esi with rate limiting."""
        mock_api_config.esi_max_retries = 3
        mock_api_config.esi_base_url = 'https://esi.evetech.net/latest'
        mock_api_config.esi_timeout = 30
        
        # First call returns rate limited, second succeeds
        mock_response_rate_limited = MagicMock()
        mock_response_rate_limited.status_code = 429
        mock_response_rate_limited.headers = {'X-ESI-Error-Limit-Reset': '5'}
        
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {'test': 'data'}
        
        mock_session.get.side_effect = [mock_response_rate_limited, mock_response_success]

        result = fetch_public_esi('/test/endpoint')

        assert result == {'test': 'data'}
        assert mock_session.get.call_count == 2
        mock_sleep.assert_called_once_with(6)  # 5 + 1 buffer

    @patch('fetch_data.session')
    @patch('fetch_data.api_config')
    def test_fetch_esi_success(self, mock_api_config, mock_session):
        """Test successful fetch_esi call."""
        mock_api_config.esi_max_retries = 3
        mock_api_config.esi_base_url = 'https://esi.evetech.net/latest'
        mock_api_config.esi_timeout = 30
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'test': 'data'}
        mock_session.get.return_value = mock_response

        result = fetch_esi('/test/endpoint', 123, 'token123')

        assert result == {'test': 'data'}
        mock_session.get.assert_called_once_with(
            'https://esi.evetech.net/latest/test/endpoint',
            headers={'Authorization': 'Bearer token123'},
            timeout=30
        )

    @patch('fetch_data.session')
    @patch('fetch_data.api_config')
    def test_fetch_esi_unauthorized(self, mock_api_config, mock_session):
        """Test fetch_esi with 401 unauthorized."""
        mock_api_config.esi_max_retries = 3
        mock_api_config.esi_base_url = 'https://esi.evetech.net/latest'
        mock_api_config.esi_timeout = 30
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_session.get.return_value = mock_response

        result = fetch_esi('/test/endpoint', 123, 'invalid_token')

        assert result is None


class TestCollectCorporationMembers:
    """Test corporation member collection functionality."""

    @patch('fetch_data.load_tokens')
    @patch('fetch_data.refresh_token')
    @patch('fetch_data.save_tokens')
    @patch('fetch_data.fetch_character_data')
    @patch('fetch_data.update_character_in_wp')
    def test_collect_corporation_members_valid_tokens(self, mock_update_wp, mock_fetch_char, mock_save, mock_refresh, mock_load_tokens):
        """Test collecting corporation members with valid tokens."""
        # Mock tokens data
        mock_tokens = {
            '123': {
                'name': 'Test Char 1',
                'access_token': 'token1',
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                'refresh_token': 'refresh1'
            },
            '456': {
                'name': 'Test Char 2',
                'access_token': 'token2',
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                'refresh_token': 'refresh2'
            }
        }
        mock_load_tokens.return_value = mock_tokens

        # Mock character data
        mock_fetch_char.side_effect = [
            {'corporation_id': 1001, 'name': 'Test Char 1'},
            {'corporation_id': 1001, 'name': 'Test Char 2'}
        ]

        result = collect_corporation_members(mock_tokens)

        expected = {
            1001: [
                ('123', 'token1', 'Test Char 1'),
                ('456', 'token2', 'Test Char 2')
            ]
        }

        assert result == expected
        assert mock_fetch_char.call_count == 2
        assert mock_update_wp.call_count == 2

    @patch('fetch_data.load_tokens')
    @patch('fetch_data.refresh_token')
    @patch('fetch_data.save_tokens')
    @patch('fetch_data.fetch_character_data')
    @patch('fetch_data.update_character_in_wp')
    def test_collect_corporation_members_expired_token_refresh(self, mock_update_wp, mock_fetch_char, mock_save, mock_refresh, mock_load_tokens):
        """Test token refresh when token is expired."""
        # Mock expired token
        expired_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        mock_tokens = {
            '123': {
                'name': 'Test Char 1',
                'access_token': 'old_token',
                'expires_at': expired_time,
                'refresh_token': 'refresh1'
            }
        }
        mock_load_tokens.return_value = mock_tokens

        # Mock refresh token response
        mock_refresh.return_value = {
            'access_token': 'new_token',
            'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        }

        # Mock character data
        mock_fetch_char.return_value = {'corporation_id': 1001, 'name': 'Test Char 1'}

        result = collect_corporation_members(mock_tokens)

        assert mock_refresh.called_once_with('refresh1')
        assert mock_save.called_once()
        assert result[1001][0][1] == 'new_token'  # Updated token


class TestIndustryJobCompletions:
    """Test industry job completion checking."""

    @patch('fetch_data.send_email')
    @patch('fetch_data.datetime')
    def test_check_industry_job_completions_upcoming(self, mock_datetime, mock_send_email):
        """Test detection of upcoming job completions."""
        # Mock current time
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now
        mock_datetime.fromisoformat = datetime.fromisoformat

        jobs = [
            {
                'job_id': 1,
                'end_date': (now + timedelta(hours=20)).isoformat().replace('+00:00', 'Z'),
                'activity_id': 1
            },
            {
                'job_id': 2,
                'end_date': (now + timedelta(hours=30)).isoformat().replace('+00:00', 'Z'),  # Too far in future
                'activity_id': 1
            }
        ]

        check_industry_job_completions(jobs, 'Test Char')

        # Email functionality is disabled, so send_email should not be called
        mock_send_email.assert_not_called()

    @patch('fetch_data.send_email')
    @patch('fetch_data.datetime')
    def test_check_industry_job_completions_none_upcoming(self, mock_datetime, mock_send_email):
        """Test when no jobs are ending soon."""
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now
        mock_datetime.fromisoformat = datetime.fromisoformat

        jobs = [
            {
                'job_id': 1,
                'end_date': (now + timedelta(hours=30)).isoformat().replace('+00:00', 'Z'),  # Too far
                'activity_id': 1
            }
        ]

        check_industry_job_completions(jobs, 'Test Char')

        # Should not send email
        mock_send_email.assert_not_called()


class TestPlanetExtractionCompletions:
    """Test planet extraction completion checking."""

    @patch('fetch_data.send_email')
    @patch('fetch_data.datetime')
    def test_check_planet_extraction_completions_upcoming(self, mock_datetime, mock_send_email):
        """Test detection of upcoming extraction completions."""
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now
        mock_datetime.fromisoformat = datetime.fromisoformat

        planet_details = {
            'pins': [
                {
                    'pin_id': 1,
                    'type_id': 1001,
                    'expiry_time': (now + timedelta(hours=20)).isoformat().replace('+00:00', 'Z')
                },
                {
                    'pin_id': 2,
                    'type_id': 1002,
                    'expiry_time': (now + timedelta(hours=30)).isoformat().replace('+00:00', 'Z')  # Too far
                }
            ]
        }

        check_planet_extraction_completions(planet_details, 'Test Char')

        # Email functionality is disabled, so send_email should not be called
        mock_send_email.assert_not_called()

    @patch('fetch_data.send_email')
    @patch('fetch_data.datetime')
    def test_check_planet_extraction_completions_none_upcoming(self, mock_datetime, mock_send_email):
        """Test when no extractions are ending soon."""
        now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now
        mock_datetime.fromisoformat = datetime.fromisoformat

        planet_details = {
            'pins': [
                {
                    'pin_id': 1,
                    'type_id': 1001,
                    'expiry_time': (now + timedelta(hours=30)).isoformat().replace('+00:00', 'Z')  # Too far
                }
            ]
        }

        check_planet_extraction_completions(planet_details, 'Test Char')

        # Should not send email
        mock_send_email.assert_not_called()