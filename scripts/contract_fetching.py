"""
EVE Observer Contract Fetching
Handles fetching contract data from ESI API.
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import aiohttp

from api_client import (
    fetch_esi,
    fetch_public_contracts_async,
    fetch_public_esi,
    get_session,
    validate_api_response,
    validate_input_params,
)
from config import CACHE_DIR, ESI_BASE_URL

logger = logging.getLogger(__name__)

# Constants
FORGE_REGION_ID = 10000002


async def _fetch_universe_data(sess, endpoint: str) -> Optional[Dict[str, Any]]:
    """Fetch data from ESI universe endpoints with error handling."""
    try:
        async with sess.get(
            f"{ESI_BASE_URL}{endpoint}",
            headers={"Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            response.raise_for_status()
            return await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


async def _get_region_from_system_id(sess, system_id: int) -> Optional[int]:
    """Get region ID from solar system ID."""
    system_data = await _fetch_universe_data(sess, f"/universe/systems/{system_id}")
    if not system_data:
        return None

    constellation_id = system_data.get("constellation_id")
    if not constellation_id:
        return None

    constellation_data = await _fetch_universe_data(sess, f"/universe/constellations/{constellation_id}")
    if not constellation_data:
        return None

    return constellation_data.get("region_id")


@validate_input_params((int, type(None)))
async def get_region_from_location(location_id: Optional[int]) -> Optional[int]:
    """Get region ID from a location ID (station or structure) with caching.

    Determines the region containing a station or structure by traversing the
    EVE universe hierarchy: location -> solar system -> constellation -> region.

    Args:
        location_id: Station ID (< 10^12) or structure ID (>= 10^12)

    Returns:
        Region ID if found, None if location cannot be resolved

    Note:
        Results are cached in 'cache/region_cache.json' to avoid repeated ESI calls.
        Structure lookups require appropriate access permissions.
    """
    if not location_id:
        return None

    # Load cache
    cache_file = os.path.join(CACHE_DIR, "region_cache.json")
    try:
        with open(cache_file, "r") as f:
            region_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        region_cache = {}

    location_id_str = str(location_id)
    if location_id_str in region_cache:
        return region_cache[location_id_str]

    region_id = None
    sess = await get_session()

    # Determine solar system ID based on location type
    solar_system_id = None
    if location_id >= 1000000000000:  # Structure
        struct_data = await _fetch_universe_data(sess, f"/universe/structures/{location_id}")
        if struct_data:
            solar_system_id = struct_data.get("solar_system_id")
    else:  # Station
        station_data = await _fetch_universe_data(sess, f"/universe/stations/{location_id}")
        if station_data:
            solar_system_id = station_data.get("system_id")

    if solar_system_id:
        region_id = await _get_region_from_system_id(sess, solar_system_id)

    # Cache the result
    if region_id:
        region_cache[location_id_str] = region_id
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(region_cache, f, indent=2)

    return region_id


async def get_issuer_names(issuer_ids: List[int]) -> Dict[int, str]:
    """Resolve issuer IDs to names using ESI universe/names endpoint.

    Batches ID resolution requests to minimize API calls and caches results.

    Args:
        issuer_ids: List of character/corporation IDs to resolve

    Returns:
        Dictionary mapping IDs to resolved names

    Note:
        Uses POST to /universe/names/ for batch resolution.
        Results are not cached as names can change.
    """
    if not issuer_ids:
        return {}

    # Remove duplicates while preserving order
    unique_ids = list(dict.fromkeys(issuer_ids))

    name_map = {}
    sess = await get_session()

    # Process in batches of 1000 (ESI limit)
    batch_size = 1000
    for i in range(0, len(unique_ids), batch_size):
        batch_ids = unique_ids[i : i + batch_size]

        try:
            async with sess.post(
                f"{ESI_BASE_URL}/universe/names/",
                json=batch_ids,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                names_data = await response.json()

                # Build mapping from response
                for name_info in names_data:
                    entity_id = name_info.get("id")
                    name = name_info.get("name")
                    if entity_id and name:
                        name_map[entity_id] = name

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"Failed to resolve names for batch {i//batch_size + 1}: {e}")

    return name_map


@validate_api_response
@validate_input_params(int, int, str)
async def fetch_character_contract_items(
    char_id: int, contract_id: int, access_token: str
) -> Optional[List[Dict[str, Any]]]:
    """Fetch items contained in a specific character contract.

    Requires the character to have access to view the contract details.

    Args:
        char_id: EVE character ID
        contract_id: EVE contract ID
        access_token: Valid ESI access token for the character

    Returns:
        List of contract item dictionaries if successful, None if access denied or failed
    """
    endpoint = f"/characters/{char_id}/contracts/{contract_id}/items/"
    return await fetch_esi(endpoint, char_id, access_token)


@validate_api_response
@validate_input_params(int, int, str)
async def fetch_corporation_contract_items(
    corp_id: int, contract_id: int, access_token: str
) -> Optional[List[Dict[str, Any]]]:
    """Fetch items contained in a specific corporation contract.

    Requires corporation access permissions for the character with the access token.

    Args:
        corp_id: EVE corporation ID
        contract_id: EVE contract ID
        access_token: Valid ESI access token for a corporation member with appropriate roles

    Returns:
        List of contract item dictionaries if successful, None if access denied or failed
    """
    endpoint = f"/corporations/{corp_id}/contracts/{contract_id}/items/"
    return await fetch_esi(endpoint, None, access_token)  # Corp endpoint doesn't need char_id


@validate_api_response
@validate_input_params(int, str)
async def fetch_character_contracts(char_id: int, access_token: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch character contracts from ESI.

    Retrieves all contracts the character is involved in, including contracts
    they've issued, accepted, or have access to.

    Args:
        char_id: EVE character ID to fetch contracts for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[List[Dict[str, Any]]]: Contracts data array if successful.
    """
    endpoint = f"/characters/{char_id}/contracts/"
    return await fetch_esi(endpoint, char_id, access_token)


@validate_api_response
@validate_input_params(int, str)
async def fetch_corporation_contracts(corp_id: int, access_token: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch corporation contracts from ESI.

    Retrieves all contracts issued by the corporation, including item exchanges,
    auctions, courier contracts, and other contract types.

    Args:
        corp_id: EVE corporation ID to fetch contracts for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[List[Dict[str, Any]]]: Contracts data array if successful.
    """
    endpoint = f"/corporations/{corp_id}/contracts/"
    return await fetch_esi(endpoint, None, access_token)  # Corp contracts don't need char_id


async def fetch_all_contracts_in_region(region_id: int) -> List[Dict[str, Any]]:
    """Fetch all contracts from a region with safety limits."""
    logger.info(f"Fetching all contracts from region {region_id}")

    all_contracts = []
    page = 1
    max_pages = 100  # Increased safety limit
    max_contracts = 50000  # Configurable limit to prevent excessive memory usage

    while page <= max_pages:
        logger.info(f"Fetching page {page}...")
        contracts = await fetch_public_contracts_async(region_id, page=page)

        if not contracts:
            logger.info(f"No more contracts or invalid response on page {page}, stopping")
            break

        logger.info(f"Found {len(contracts)} contracts on page {page}")

        # Debug: print types of first 5 contracts
        if page == 1:
            for i, c in enumerate(contracts[:5]):
                logger.info(f"Contract {i}: type={c.get('type')}, status={c.get('status')}, price={c.get('price')}")

        # Validate and store contracts
        for contract in contracts:
            if not isinstance(contract, dict) or "contract_id" not in contract:
                logger.warning(f"Invalid contract data on page {page}: {contract}")
                continue

            contract_id = contract["contract_id"]
            contract_type = contract.get("type")

            contract_data = {
                "contract_id": contract_id,
                "type": contract_type,
                "price": contract.get("price", 0),
                "issuer_id": contract.get("issuer_id"),
                "issuer_corporation_id": contract.get("issuer_corporation_id"),
                "start_location_id": contract.get("start_location_id"),
                "title": contract.get("title", ""),
                "date_issued": contract.get("date_issued"),
                "date_expired": contract.get("date_expired"),
                "volume": contract.get("volume", 1),
                "status": "outstanding",  # Public endpoint only returns active contracts
            }

            all_contracts.append(contract_data)
            logger.debug(f"Stored contract {contract_id} of type {contract_type}")

            # Check contract limit
            if len(all_contracts) >= max_contracts:
                logger.warning(f"Reached contract limit of {max_contracts}, stopping")
                return all_contracts

        page += 1

    logger.info(f"Total contracts found: {len(all_contracts)}")
    return all_contracts
