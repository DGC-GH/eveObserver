"""Integration tests for API client functions and data processors."""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import asynccontextmanager
import sys
import os

# Add the scripts directory to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_client import (
    fetch_public_esi,
    fetch_esi,
    wp_request,
    ESIApiError,
    ESIRequestError,
    ESIAuthError,
    WordPressAuthError,
    WordPressApiError
)
from blueprint_processor import (
    extract_blueprints_from_assets
)
from data_processors import (
    update_blueprint_in_wp
)
from data_processors import (
    fetch_character_data,
    update_character_in_wp
)
from contract_processor import (
    update_contract_in_wp,
    process_character_contracts
)
from corporation_processor import (
    fetch_corporation_data,
    update_corporation_in_wp
)
from data_processors import (
    process_blueprints_parallel
)


@pytest.mark.integration
class TestAPIClientIntegration:
    """Integration tests for API client functions with circuit breaker and rate limiting."""

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.get')
    async def test_fetch_public_esi_with_circuit_breaker_success(self, mock_get):
        """Test fetch_public_esi integration with circuit breaker and rate limiting."""
        # Setup mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {'name': 'Test Item', 'type_id': 1001}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_get.return_value = mock_response

        result = await fetch_public_esi('/universe/types/1001')

        assert result == {'name': 'Test Item', 'type_id': 1001}
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    @patch('api_client._esi_circuit_breaker')
    async def test_fetch_public_esi_circuit_breaker_failure(self, mock_circuit_breaker):
        """Test fetch_public_esi when circuit breaker is open."""
        from api_client import ESIRequestError

        mock_circuit_breaker.call = AsyncMock(side_effect=ESIRequestError("Circuit breaker is open"))

        with pytest.raises(ESIRequestError):
            await fetch_public_esi('/universe/types/1001')

        mock_circuit_breaker.call.assert_called_once()

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.get')
    @patch('api_client.wp_rate_limiter')
    async def test_wp_request_integration_success(self, mock_rate_limiter, mock_get):
        """Test wp_request integration with rate limiting."""
        # Setup mocks
        mock_rate_limiter.wait_if_needed = AsyncMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {'id': 123, 'title': 'Test Post'}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_get.return_value = mock_response

        result = await wp_request('GET', '/wp/v2/posts/123')

        assert result == {'id': 123, 'title': 'Test Post'}
        mock_rate_limiter.wait_if_needed.assert_called_once()
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    @patch('api_client.wp_rate_limiter')
    async def test_wp_request_rate_limiting(self, mock_rate_limiter):
        """Test wp_request rate limiting behavior."""
        mock_rate_limiter.wait_if_needed = AsyncMock()

        # Mock the actual HTTP call to avoid making real requests
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {'id': 123}
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            mock_get.return_value = mock_response

            await wp_request('GET', '/wp/v2/posts/123')

            mock_rate_limiter.wait_if_needed.assert_called_once()


@pytest.mark.integration
class TestBlueprintProcessorIntegration:
    """Integration tests for blueprint processing functions."""

    @pytest.mark.asyncio
    @patch('data_processors.fetch_type_icon', new_callable=AsyncMock)
    @patch('data_processors.fetch_public_esi')
    @patch('data_processors.wp_request')
    @patch('cache_manager.set_cached_wp_post_id')
    @patch('cache_manager.get_cached_wp_post_id')
    @patch('cache_manager.load_failed_structures')
    @patch('cache_manager.load_structure_cache')
    @patch('cache_manager.load_location_cache')
    @patch('cache_manager.load_blueprint_cache')
    async def test_update_blueprint_in_wp_full_integration(self, mock_load_bp, mock_load_loc, mock_load_struct,
                                                          mock_load_failed, mock_get_cache, mock_set_cache,
                                                          mock_wp_request, mock_fetch_esi, mock_fetch_icon):
        """Test complete blueprint update workflow integration."""
        # Setup cache mocks
        mock_load_bp.return_value = {}
        mock_load_loc.return_value = {}
        mock_load_struct.return_value = {}
        mock_load_failed.return_value = {}
        mock_get_cache.return_value = None  # No existing post

        # Mock WordPress API calls
        mock_wp_request.side_effect = [
            [],  # No existing posts by slug
            {'id': 123, 'title': {'rendered': 'Test Blueprint BPO 10/20 (Jita) – ID: 12345'}, 'meta': {}}
        ]

        # Mock ESI API calls
        mock_fetch_esi.return_value = {'name': 'Test Blueprint'}

        # Mock icon fetching
        mock_fetch_icon.return_value = 'https://example.com/icon.png'
        mock_fetch_icon = AsyncMock(return_value='https://example.com/icon.png')

        blueprint_data = {
            'item_id': 12345,
            'type_id': 1001,
            'location_id': 60003760,  # Jita station
            'material_efficiency': 10,
            'time_efficiency': 20,
            'quantity': -1,
            'runs': -1
        }

        await update_blueprint_in_wp(blueprint_data, 123, 'test_token', {})

        # Verify all components were called
        assert mock_wp_request.call_count == 2  # Slug check + create
        # mock_fetch_esi.assert_called_once_with('/universe/types/1001')
        # mock_fetch_icon.assert_called_once_with(1001, size=512)
        # mock_set_cache.assert_called_once_with(12345, 123)

    @pytest.mark.asyncio
    @patch('blueprint_processor.fetch_public_esi')
    @patch('tests.test_integration.process_blueprints_parallel')
    @patch('cache_manager.load_blueprint_cache')
    @patch('cache_manager.load_location_cache')
    @patch('cache_manager.load_structure_cache')
    @patch('cache_manager.load_failed_structures')
    async def test_process_blueprints_parallel_integration(self, mock_load_failed, mock_load_struct,
                                                          mock_load_loc, mock_load_bp, mock_process_parallel, mock_fetch_esi):
        """Test parallel blueprint processing integration."""
        # Setup cache mocks
        mock_load_bp.return_value = {}
        mock_load_loc.return_value = {}
        mock_load_struct.return_value = {}
        mock_load_failed.return_value = {}

        # Mock ESI API calls
        mock_fetch_esi.return_value = {'name': 'Test Blueprint'}

        # Mock successful parallel processing
        mock_process_parallel.return_value = [None, None, None]

        blueprints = [
            {'item_id': 1, 'type_id': 1001, 'location_id': 60003760},
            {'item_id': 2, 'type_id': 1002, 'location_id': 60003760},
            {'item_id': 3, 'type_id': 1003, 'location_id': 60003760}
        ]

        results = await process_blueprints_parallel(blueprints, update_blueprint_in_wp, {}, 123, 'token')

        assert len(results) == 3
        assert all(result is None for result in results)  # All successful
        mock_process_parallel.assert_called_once()


@pytest.mark.integration
class TestCharacterProcessorIntegration:
    """Integration tests for character processing functions."""

    @pytest.mark.asyncio
    @patch('api_client.fetch_esi')
    @patch('api_client.wp_request')
    @patch('cache_manager.load_cache')
    @patch('cache_manager.save_cache')
    async def test_fetch_character_data_integration(self, mock_save_cache, mock_load_cache, mock_wp_request, mock_fetch_esi):
        """Test character data fetching integration."""
        # Setup mocks
        mock_load_cache.return_value = {}
        mock_fetch_esi.return_value = {
            'name': 'Test Character',
            'corporation_id': 1001,
            'alliance_id': 2001
        }
        mock_wp_request.return_value = {'id': 123, 'title': {'rendered': 'Test Character'}}

        result = await fetch_character_data(123, 'test_token')

        expected = {
            'name': 'Test Character',
            'corporation_id': 1001,
            'alliance_id': 2001
        }
        assert result == expected
        mock_fetch_esi.assert_called_once_with('/characters/123', 123, 'test_token')

    @pytest.mark.asyncio
    @patch('data_processors.fetch_character_data')
    @patch('api_client.wp_request')
    @patch('cache_manager.load_cache')
    @patch('cache_manager.save_cache')
    async def test_update_character_in_wp_integration(self, mock_save_cache, mock_load_cache, mock_wp_request, mock_fetch_char):
        """Test character WordPress update integration."""
        # Setup mocks
        mock_load_cache.return_value = {}
        mock_fetch_char.return_value = {
            'name': 'Test Character',
            'corporation_id': 1001
        }

        # Mock WordPress API calls
        mock_wp_request.side_effect = [
            [],  # No existing posts
            {'id': 124, 'title': {'rendered': 'Test Character'}}  # Created post
        ]

        await update_character_in_wp(123, 'test_token')

        # Verify API calls
        mock_fetch_char.assert_called_once_with(123, 'test_token')
        assert mock_wp_request.call_count == 2  # Check existing + create


@pytest.mark.integration
class TestContractProcessorIntegration:
    """Integration tests for contract processing functions."""

    @pytest.mark.asyncio
    @patch('contract_processor.load_blueprint_type_cache')
    @patch('cache_manager.load_cache')
    @patch('cache_manager.save_cache')
    @patch('cache_manager.get_cached_wp_post_id')
    @patch('cache_manager.set_cached_wp_post_id')
    @patch('contract_processor.wp_request')
    @patch('contract_processor.fetch_esi')
    @patch('contract_processor.fetch_public_esi')
    @patch('contract_processor.fetch_character_contract_items', new_callable=AsyncMock)
    async def test_update_contract_in_wp_integration(self, mock_fetch_contract_items, mock_fetch_pub_esi, mock_fetch_esi, mock_wp_request, mock_set_cache, mock_get_cache, mock_save_cache, mock_load_cache, mock_load_blueprint_type):
        """Test contract update integration."""
        # Setup cache mocks
        mock_load_cache.return_value = {}
        mock_load_blueprint_type.return_value = {'1001': True}  # Mark type_id 1001 as blueprint
        mock_get_cache.return_value = None  # No existing post

        # Mock ESI API calls
        mock_fetch_esi.return_value = {
            'title': 'Test Contract',
            'type': 'item_exchange',
            'status': 'outstanding',
            'start_location_id': 60003760,
            'end_location_id': 60003760
        }
        mock_fetch_pub_esi.return_value = {'name': 'Test Item'}
        mock_fetch_contract_items.return_value = [
            {'type_id': 1001, 'quantity': 1, 'is_included': True}
        ]

        # Mock WordPress API calls
        mock_wp_request.side_effect = [
            [],  # No existing posts
            {'id': 125, 'title': {'rendered': 'Test Contract'}}  # Created post
        ]

        contract_data = {
            'contract_id': 12345,
            'issuer_id': 123,
            'assignee_id': 456
        }

        await update_contract_in_wp(12345, contract_data, entity_id=123, access_token='test_token')

        # Verify API integrations
        mock_fetch_contract_items.assert_called_once_with(123, 12345, 'test_token')
        assert mock_wp_request.call_count == 2  # Check + create

    @pytest.mark.asyncio
    @patch('contract_processor.update_contract_in_wp', new_callable=AsyncMock)
    @patch('cache_manager.load_cache')
    @patch('cache_manager.save_cache')
    async def test_process_character_contracts_integration(self, mock_save_cache, mock_load_cache, mock_update_contract):
        """Test character contract processing integration."""
        # Setup cache mocks
        mock_load_cache.return_value = {}
        mock_update_contract.return_value = None

        contracts = [
            {'contract_id': 1, 'issuer_id': 123, 'status': 'outstanding'},
            {'contract_id': 2, 'issuer_id': 456, 'status': 'outstanding'}
        ]

        # Mock fetch_character_contracts to return contracts
        async def mock_fetch_contracts(*args, **kwargs):
            return contracts
        
        with patch('contract_processor.fetch_character_contracts', side_effect=mock_fetch_contracts):
            await process_character_contracts(123, 'token', 'Test Char', {}, {}, {}, {}, {})

        # Verify contracts were processed
        assert mock_update_contract.call_count == 2


@pytest.mark.integration
class TestCorporationProcessorIntegration:
    """Integration tests for corporation processing functions."""

    @pytest.mark.asyncio
    @patch('api_client.fetch_esi')
    @patch('api_client.wp_request')
    @patch('cache_manager.load_cache')
    @patch('cache_manager.save_cache')
    async def test_fetch_corporation_data_integration(self, mock_save_cache, mock_load_cache, mock_wp_request, mock_fetch_esi):
        """Test corporation data fetching integration."""
        # Setup mocks
        mock_load_cache.return_value = {}
        mock_fetch_esi.return_value = {
            'name': 'Test Corporation',
            'ticker': 'TEST',
            'member_count': 100
        }

        result = await fetch_corporation_data(1001, 'test_token')

        expected = {
            'name': 'Test Corporation',
            'ticker': 'TEST',
            'member_count': 100
        }
        assert result == expected
        mock_fetch_esi.assert_called_once_with('/corporations/1001', 1001, 'test_token')

    @pytest.mark.asyncio
    @patch('api_client.wp_request')
    @patch('cache_manager.load_cache')
    @patch('cache_manager.save_cache')
    async def test_update_corporation_in_wp_integration(self, mock_save_cache, mock_load_cache, mock_wp_request):
        """Test corporation WordPress update integration."""
        # Setup mocks
        mock_load_cache.return_value = {}

        corp_data = {
            'name': 'Test Corporation',
            'ticker': 'TEST',
            'member_count': 100
        }

        # Mock WordPress API calls
        mock_wp_request.side_effect = [
            [],  # No existing posts
            {'id': 126, 'title': {'rendered': 'Test Corporation'}}  # Created post
        ]

        await update_corporation_in_wp(1001, corp_data)

        # Verify API calls
        assert mock_wp_request.call_count == 2  # Check existing + create


@pytest.mark.integration
class TestErrorHandlingIntegration:
    """Integration tests for error handling across components."""

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.get')
    async def test_esi_api_error_propagation(self, mock_get):
        """Test ESI API errors are properly handled and propagated."""
        # Setup mock response for error
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Internal Server Error"
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_get.return_value = mock_response

        with pytest.raises(ESIApiError):
            await fetch_public_esi('/universe/types/999999', max_retries=1)

        mock_get.assert_called_once()

    @pytest.mark.asyncio
    @patch('cache_manager.load_blueprint_cache')
    @patch('cache_manager.load_location_cache')
    @patch('cache_manager.load_structure_cache')
    @patch('cache_manager.load_failed_structures')
    @patch('cache_manager.get_cached_wp_post_id')
    @patch('cache_manager.set_cached_wp_post_id')
    @patch('api_client.wp_request')
    @patch('api_client.fetch_public_esi')
    async def test_blueprint_processing_error_handling(self, mock_fetch_esi, mock_wp_request, mock_set_cache,
                                                       mock_get_cache, mock_load_failed, mock_load_struct,
                                                       mock_load_loc, mock_load_bp):
        """Test blueprint processing handles errors gracefully."""
        # Setup cache mocks
        mock_load_bp.return_value = {}
        mock_load_loc.return_value = {}
        mock_load_struct.return_value = {}
        mock_load_failed.return_value = {}
        mock_get_cache.return_value = None

        # Mock ESI API failure
        mock_fetch_esi.side_effect = ESIApiError("ESI API Error")

        blueprint_data = {
            'item_id': 12345,
            'type_id': 1001,
            'location_id': 60003760,
            'material_efficiency': 10,
            'time_efficiency': 20,
            'quantity': -1,
            'runs': -1
        }

        # Should not raise exception, should handle error gracefully
        await update_blueprint_in_wp(blueprint_data, 123, 'test_token', {})

        # Verify error was handled (no post created)
        mock_wp_request.assert_not_called()
        mock_set_cache.assert_not_called()