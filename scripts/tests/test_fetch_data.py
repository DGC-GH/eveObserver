"""Tests for fetch_data.py functions."""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import sys
import os

# Add the scripts directory to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_data import (
    collect_corporation_members,
)
from api_client import (
    ApiConfig,
)
from character_processor import (
    check_industry_job_completions,
    check_planet_extraction_completions,
)
from api_client import (
    fetch_public_esi,
    fetch_esi,
    ESIApiError,
    ESIRequestError,
    ESIAuthError
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

    @pytest.mark.asyncio
    @patch('api_client.get_session')
    @patch('api_client.api_config')
    async def test_fetch_public_esi_success(self, mock_api_config, mock_get_session):
        """Test successful fetch_public_esi call."""
        # Setup mocks
        mock_api_config.esi_max_retries = 3
        mock_api_config.esi_base_url = 'https://esi.evetech.net/latest'
        mock_api_config.esi_timeout = 30

        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {'test': 'data'}

        # Create an async context manager
        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            yield mock_response

        mock_session.get = mock_get
        mock_get_session.return_value = mock_session

        result = await fetch_public_esi('/test/endpoint')

        assert result == {'test': 'data'}

    @pytest.mark.asyncio
    @patch('api_client.get_session')
    @patch('api_client.api_config')
    async def test_fetch_public_esi_404(self, mock_api_config, mock_get_session):
        """Test fetch_public_esi with 404 response."""
        mock_api_config.esi_max_retries = 3
        mock_api_config.esi_base_url = 'https://esi.evetech.net/latest'
        mock_api_config.esi_timeout = 30

        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.text.return_value = "Not Found"

        # Create an async context manager
        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            yield mock_response

        mock_session.get = mock_get
        mock_get_session.return_value = mock_session

        with pytest.raises(ESIRequestError):
            await fetch_public_esi('/test/endpoint')

    @pytest.mark.asyncio
    @patch('asyncio.sleep')
    @patch('api_client.get_session')
    @patch('api_client.api_config')
    async def test_fetch_public_esi_rate_limit(self, mock_api_config, mock_get_session, mock_sleep):
        """Test fetch_public_esi with rate limiting."""
        mock_api_config.esi_max_retries = 3
        mock_api_config.esi_base_url = 'https://esi.evetech.net/latest'
        mock_api_config.esi_timeout = 30

        mock_session = AsyncMock()

        # First call returns rate limited, second succeeds
        mock_response_rate_limited = AsyncMock()
        mock_response_rate_limited.status = 429
        mock_response_rate_limited.headers = {'X-ESI-Error-Limit-Reset': '5'}
        mock_response_rate_limited.text.return_value = "Rate Limited"

        mock_response_success = AsyncMock()
        mock_response_success.status = 200
        mock_response_success.json.return_value = {'test': 'data'}

        call_count = 0
        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield mock_response_rate_limited
            else:
                yield mock_response_success

        mock_session.get = mock_get
        mock_get_session.return_value = mock_session

        result = await fetch_public_esi('/test/endpoint')

        assert result == {'test': 'data'}
        assert call_count == 2
        mock_sleep.assert_called_once_with(6)  # 5 + 1 buffer

    @pytest.mark.asyncio
    @patch('api_client.get_session')
    @patch('api_client.api_config')
    async def test_fetch_esi_success(self, mock_api_config, mock_get_session):
        """Test successful fetch_esi call."""
        mock_api_config.esi_max_retries = 3
        mock_api_config.esi_base_url = 'https://esi.evetech.net/latest'
        mock_api_config.esi_timeout = 30

        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {'test': 'data'}

        # Create an async context manager
        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            yield mock_response

        mock_session.get = mock_get
        mock_get_session.return_value = mock_session

        result = await fetch_esi('/test/endpoint', 123, 'token123')

        assert result == {'test': 'data'}

    @pytest.mark.asyncio
    @patch('api_client.get_session')
    @patch('api_client.api_config')
    async def test_fetch_esi_unauthorized(self, mock_api_config, mock_get_session):
        """Test fetch_esi with 401 unauthorized."""
        mock_api_config.esi_max_retries = 3
        mock_api_config.esi_base_url = 'https://esi.evetech.net/latest'
        mock_api_config.esi_timeout = 30

        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text.return_value = "Unauthorized"

        # Create an async context manager
        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            yield mock_response

        mock_session.get = mock_get
        mock_get_session.return_value = mock_session

        with pytest.raises(ESIAuthError):
            await fetch_esi('/test/endpoint', 123, 'invalid_token')


class TestCollectCorporationMembers:
    """Test corporation member collection functionality."""

    @patch('fetch_data.load_tokens')
    @patch('fetch_data.refresh_token')
    @patch('fetch_data.save_tokens')
    @patch('fetch_data.fetch_character_data')
    @patch('fetch_data.update_character_in_wp')
    @pytest.mark.asyncio
    async def test_collect_corporation_members_valid_tokens(self, mock_update_wp, mock_fetch_char, mock_save, mock_refresh, mock_load_tokens):
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
        async def async_return_1():
            return {'corporation_id': 1001, 'name': 'Test Char 1'}
        async def async_return_2():
            return {'corporation_id': 1001, 'name': 'Test Char 2'}
        
        mock_fetch_char.side_effect = [async_return_1(), async_return_2()]

        result = await collect_corporation_members(mock_tokens)

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
    @pytest.mark.asyncio
    async def test_collect_corporation_members_expired_token_refresh(self, mock_update_wp, mock_fetch_char, mock_save, mock_refresh, mock_load_tokens):
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
        async def async_return(char_id, access_token):
            return {'corporation_id': 1001, 'name': 'Test Char 1'}
        
        mock_fetch_char.side_effect = async_return

        result = await collect_corporation_members(mock_tokens)

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


class TestBlueprintProcessing:
    """Test blueprint processing functionality."""

    @pytest.mark.asyncio
    @patch('data_processors.load_blueprint_cache')
    @patch('data_processors.load_location_cache')
    @patch('data_processors.load_structure_cache')
    @patch('data_processors.load_failed_structures')
    @patch('data_processors.load_wp_post_id_cache')
    @patch('data_processors.get_cached_wp_post_id')
    @patch('data_processors.wp_request')
    @patch('data_processors.fetch_public_esi')
    @patch('data_processors.fetch_type_icon')
    @patch('data_processors.set_cached_wp_post_id')
    async def test_update_blueprint_in_wp_new_blueprint(self, mock_set_cache, mock_fetch_icon, mock_fetch_esi, mock_wp_request, mock_get_cache, mock_load_wp_cache, mock_load_failed, mock_load_struct, mock_load_loc, mock_load_bp):
        """Test creating a new blueprint post."""
        from data_processors import update_blueprint_in_wp

        # Setup mocks
        mock_load_bp.return_value = {}
        mock_load_loc.return_value = {}
        mock_load_struct.return_value = {}
        mock_load_failed.return_value = {}
        mock_load_wp_cache.return_value = {}
        mock_get_cache.return_value = None  # No cached post ID

        # Mock WP request for slug lookup - no existing post
        mock_wp_request.side_effect = [
            [],  # No existing posts by slug
            {'id': 123, 'title': {'rendered': 'Test Blueprint BPO 10/20 (Test Station) – ID: 12345'}, 'meta': {}}  # Created post
        ]

        # Mock ESI fetch for type data
        mock_fetch_esi.return_value = {'name': 'Test Blueprint'}

        # Mock icon fetch
        async def mock_icon_func(*args, **kwargs):
            return 'https://example.com/icon.png'
        mock_fetch_icon.side_effect = mock_icon_func

        blueprint_data = {
            'item_id': 12345,
            'type_id': 1001,
            'location_id': 60003760,  # Station ID
            'material_efficiency': 10,
            'time_efficiency': 20,
            'quantity': -1,
            'runs': -1
        }

        await update_blueprint_in_wp(blueprint_data, 123, 'token')

        # Verify WP requests
        assert mock_wp_request.call_count == 2
        # First call: get existing by slug
        # Second call: create new post

        # Verify icon was fetched for new blueprint
        mock_fetch_icon.assert_called_once_with(1001, size=512)

    @pytest.mark.asyncio
    @patch('data_processors.load_blueprint_cache')
    @patch('data_processors.load_location_cache')
    @patch('data_processors.load_structure_cache')
    @patch('data_processors.load_failed_structures')
    @patch('data_processors.load_wp_post_id_cache')
    @patch('data_processors.get_cached_wp_post_id')
    @patch('data_processors.wp_request')
    @patch('data_processors.fetch_public_esi')
    @patch('data_processors.fetch_esi')
    async def test_update_blueprint_in_wp_structure_location(self, mock_fetch_esi_auth, mock_fetch_esi_pub, mock_wp_request, mock_get_cache, mock_load_wp_cache, mock_load_failed, mock_load_struct, mock_load_loc, mock_load_bp):
        """Test blueprint processing with structure location."""
        from data_processors import update_blueprint_in_wp

        # Setup mocks
        mock_load_bp.return_value = {}
        mock_load_loc.return_value = {}
        mock_load_struct.return_value = {}
        mock_load_failed.return_value = {}
        mock_load_wp_cache.return_value = {}
        mock_get_cache.return_value = None

        # Mock WP requests
        mock_wp_request.side_effect = [
            [],  # No existing posts
            {'id': 123, 'title': {'rendered': 'Test Blueprint BPO 0/0 (Test Citadel) – ID: 12345'}, 'meta': {}}
        ]

        # Mock ESI fetches
        mock_fetch_esi_pub.side_effect = [
            {'name': 'Test Blueprint'},  # Type data
            {'name': 'Test Citadel'}     # Structure data
        ]

        blueprint_data = {
            'item_id': 12345,
            'type_id': 1001,
            'location_id': 1035469615808,  # Structure ID (> 10^12)
            'material_efficiency': 0,
            'time_efficiency': 0,
            'quantity': -1,
            'runs': -1
        }

        await update_blueprint_in_wp(blueprint_data, 123, 'token')

        # Verify structure fetch was called
        mock_fetch_esi_auth.assert_called_once_with('/universe/structures/1035469615808', 123, 'token')

    @pytest.mark.asyncio
    @patch('data_processors.update_blueprint_in_wp')
    @patch('data_processors.load_blueprint_cache')
    @patch('data_processors.load_location_cache')
    @patch('data_processors.load_structure_cache')
    @patch('data_processors.load_failed_structures')
    @patch('data_processors.load_wp_post_id_cache')
    async def test_process_blueprints_parallel_success(self, mock_load_wp_cache, mock_load_failed, mock_load_struct, mock_load_loc, mock_load_bp, mock_update_bp):
        """Test parallel blueprint processing with successful updates."""
        from data_processors import process_blueprints_parallel

        # Setup mocks
        mock_load_bp.return_value = {}
        mock_load_loc.return_value = {}
        mock_load_struct.return_value = {}
        mock_load_failed.return_value = {}
        mock_load_wp_cache.return_value = {}

        mock_update_bp.return_value = None  # Success

        blueprints = [
            {'item_id': 1, 'type_id': 1001},
            {'item_id': 2, 'type_id': 1002},
            {'item_id': 3, 'type_id': 1003}
        ]

        results = await process_blueprints_parallel(blueprints, mock_update_bp, {}, 123, 'token')

        assert len(results) == 3
        assert mock_update_bp.call_count == 3

    @pytest.mark.asyncio
    @patch('data_processors.update_blueprint_in_wp')
    @patch('data_processors.load_blueprint_cache')
    @patch('data_processors.load_location_cache')
    @patch('data_processors.load_structure_cache')
    @patch('data_processors.load_failed_structures')
    @patch('data_processors.load_wp_post_id_cache')
    async def test_process_blueprints_parallel_with_exceptions(self, mock_load_wp_cache, mock_load_failed, mock_load_struct, mock_load_loc, mock_load_bp, mock_update_bp):
        """Test parallel blueprint processing with some failures."""
        from data_processors import process_blueprints_parallel

        # Setup mocks
        mock_load_bp.return_value = {}
        mock_load_loc.return_value = {}
        mock_load_struct.return_value = {}
        mock_load_failed.return_value = {}
        mock_load_wp_cache.return_value = {}

        # Mock update function to succeed for first two, fail for third
        mock_update_bp.side_effect = [None, None, Exception("Test error")]

        blueprints = [
            {'item_id': 1, 'type_id': 1001},
            {'item_id': 2, 'type_id': 1002},
            {'item_id': 3, 'type_id': 1003}
        ]

        results = await process_blueprints_parallel(blueprints, mock_update_bp, {}, 123, 'token')

        assert len(results) == 3
        assert isinstance(results[2], Exception)
        assert str(results[2]) == "Test error"


class TestWordPressAPIIntegration:
    """Test WordPress API integration functionality."""

    @pytest.mark.asyncio
    @patch('api_client.get_session')
    @patch('api_client._wp_circuit_breaker')
    @patch('api_client.wp_rate_limiter')
    async def test_wp_request_get_success(self, mock_rate_limiter, mock_circuit_breaker, mock_get_session):
        """Test successful WordPress GET request."""
        from api_client import wp_request

        # Setup mocks
        mock_rate_limiter.wait_if_needed = AsyncMock()
        mock_circuit_breaker.call = AsyncMock()

        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {'id': 123, 'title': {'rendered': 'Test Post'}}

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            yield mock_response

        mock_session.get = mock_get
        mock_get_session.return_value = mock_session

        # Mock circuit breaker to call the function directly
        async def mock_call(func):
            return await func()

        mock_circuit_breaker.call.side_effect = mock_call

        result = await wp_request('GET', '/wp-json/wp/v2/posts/123')

        assert result == {'id': 123, 'title': {'rendered': 'Test Post'}}
        mock_rate_limiter.wait_if_needed.assert_called_once()

    @pytest.mark.asyncio
    @patch('api_client.get_session')
    @patch('api_client._wp_circuit_breaker')
    @patch('api_client.wp_rate_limiter')
    async def test_wp_request_post_success(self, mock_rate_limiter, mock_circuit_breaker, mock_get_session):
        """Test successful WordPress POST request."""
        from api_client import wp_request

        # Setup mocks
        mock_rate_limiter.wait_if_needed = AsyncMock()
        mock_circuit_breaker.call = AsyncMock()

        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json.return_value = {'id': 124, 'title': {'rendered': 'New Post'}}

        @asynccontextmanager
        async def mock_post(*args, **kwargs):
            yield mock_response

        mock_session.post = mock_post
        mock_get_session.return_value = mock_session

        async def mock_call(func):
            return await func()

        mock_circuit_breaker.call.side_effect = mock_call

        post_data = {'title': 'New Post', 'status': 'publish'}
        result = await wp_request('POST', '/wp-json/wp/v2/posts', post_data)

        assert result == {'id': 124, 'title': {'rendered': 'New Post'}}
        mock_rate_limiter.wait_if_needed.assert_called_once()

    @pytest.mark.asyncio
    @patch('api_client.get_session')
    @patch('api_client._wp_circuit_breaker')
    @patch('api_client.wp_rate_limiter')
    async def test_wp_request_authentication_error(self, mock_rate_limiter, mock_circuit_breaker, mock_get_session):
        """Test WordPress request with authentication error."""
        from api_client import wp_request, WordPressAuthError

        # Setup mocks
        mock_rate_limiter.wait_if_needed = AsyncMock()
        mock_circuit_breaker.call = AsyncMock()

        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text.return_value = "Unauthorized"

        @asynccontextmanager
        async def mock_get(*args, **kwargs):
            yield mock_response

        mock_session.get = mock_get
        mock_get_session.return_value = mock_session

        async def mock_call(func):
            return await func()

        mock_circuit_breaker.call.side_effect = mock_call

        with pytest.raises(WordPressAuthError):
            await wp_request('GET', '/wp-json/wp/v2/posts/123')


class TestCacheLRUOptimization:
    """Test LRU cache optimizations."""

    @patch('cache_manager.load_blueprint_cache')
    @patch('cache_manager.get_cached_value_with_stats')
    def test_get_cached_blueprint_name_lru(self, mock_get_cached, mock_load_cache):
        """Test LRU caching for blueprint name lookups."""
        from cache_manager import get_cached_blueprint_name

        mock_load_cache.return_value = {'1001': 'Test Blueprint'}
        mock_get_cached.return_value = 'Test Blueprint'

        # First call
        result1 = get_cached_blueprint_name('1001')
        assert result1 == 'Test Blueprint'

        # Second call should use LRU cache
        result2 = get_cached_blueprint_name('1001')
        assert result2 == 'Test Blueprint'

        # Verify load_cache was only called once due to LRU
        assert mock_load_cache.call_count == 1

    @patch('cache_manager.load_location_cache')
    @patch('cache_manager.get_cached_value_with_stats')
    def test_get_cached_location_name_lru(self, mock_get_cached, mock_load_cache):
        """Test LRU caching for location name lookups."""
        from cache_manager import get_cached_location_name

        mock_load_cache.return_value = {'60003760': 'Jita IV - Moon 4 - Caldari Navy Assembly Plant'}
        mock_get_cached.return_value = 'Jita IV - Moon 4 - Caldari Navy Assembly Plant'

        # First call
        result1 = get_cached_location_name('60003760')
        assert result1 == 'Jita IV - Moon 4 - Caldari Navy Assembly Plant'

        # Second call should use LRU cache
        result2 = get_cached_location_name('60003760')
        assert result2 == 'Jita IV - Moon 4 - Caldari Navy Assembly Plant'

        # Verify load_cache was only called once due to LRU
        assert mock_load_cache.call_count == 1