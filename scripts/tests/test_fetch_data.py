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
    check_planet_extraction_completions
)


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

        # Should send email for job ending in 20 hours
        mock_send_email.assert_called_once()
        subject = mock_send_email.call_args[0][0]
        assert '1 industry jobs ending soon' in subject
        assert 'Test Char' in subject

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

        # Should send email for extraction ending in 20 hours
        mock_send_email.assert_called_once()
        subject = mock_send_email.call_args[0][0]
        assert '1 PI extractions ending soon' in subject
        assert 'Test Char' in subject

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