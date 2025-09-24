import os
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from api_client import (
    fetch_esi,
    fetch_public_contract_items_async,
    fetch_public_contracts_async,
    fetch_public_esi,
    fetch_type_icon,
    get_session,
    validate_api_response,
    validate_input_params,
    wp_request,
)
from blueprint_processor import (
    extract_blueprints_from_contracts,
    update_blueprint_from_asset_in_wp,
)
from data_processors import process_blueprints_parallel
from cache_manager import (
    get_cached_blueprint_name,
    load_blueprint_cache,
    load_blueprint_type_cache,
    save_blueprint_cache,
)
from cache_manager_contracts import ContractCacheManager
from config import ESI_BASE_URL, WP_PER_PAGE, CACHE_DIR

"""
EVE Observer Contract Processor
Handles fetching and processing of EVE contract data.
"""

import logging

logger = logging.getLogger(__name__)

# Constants
FORGE_REGION_ID = 10000002


@validate_input_params(dict, list)
async def check_contract_competition(
    contract_data: Dict[str, Any], contract_items: List[Dict[str, Any]], limit_to_issuer_ids: Optional[List[int]] = None, issuer_name_filter: Optional[str] = None, all_expanded_contracts: Optional[List[Dict[str, Any]]] = None
) -> Tuple[bool, Optional[float]]:
    """Check if a sell contract has been outbid by cheaper competing contracts in the same region.

    Uses pre-expanded contract data when available, otherwise fetches contracts page by page.

    Args:
        contract_data: Contract information dictionary from ESI
        contract_items: List of items in the contract
        limit_to_issuer_ids: Optional list of issuer IDs to limit competition search to
        issuer_name_filter: Optional text to filter issuers by name (checks issuer name, corp name, and title)
        all_expanded_contracts: Optional list of pre-expanded contracts with full details

    Returns:
        Tuple of (is_outbid: bool, competing_price: float or None)
        - is_outbid: True if a cheaper competing contract exists
        - competing_price: The price per item of the cheapest competing contract, or None

    Note:
        Only checks single-item sell contracts (item_exchange type) with positive quantities.
        When all_expanded_contracts is provided, uses pre-fetched data for better performance.
    """
    if not contract_items or len(contract_items) != 1:
        return False, None  # Only check single item contracts

    contract_type = contract_data.get("type")
    if contract_type != "item_exchange":
        return False, None  # Only check sell orders

    item = contract_items[0]
    type_id = item.get("type_id")
    quantity = item.get("quantity", 1)
    is_blueprint_copy = item.get("is_blueprint_copy", False)
    contract_price = contract_data.get("price", 0)
    contract_id = contract_data.get("contract_id")
    contract_issuer_id = contract_data.get("issuer_id")

    if not type_id or quantity <= 0 or contract_price <= 0:
        return False, None

    price_per_item = contract_price / quantity

    # Get contract region
    region_id = await get_region_from_location(contract_data.get("start_location_id"))
    if not region_id:
        logger.warning(f"Could not determine region for contract {contract_id}")
        return False, None

    logger.info(
        f"Checking competition for contract {contract_id} (type_id: {type_id}, "
        f"price_per_item: {price_per_item:.2f}) in region {region_id}"
    )

    if limit_to_issuer_ids:
        logger.info(f"Limiting competition search to issuers: {limit_to_issuer_ids}")

    if issuer_name_filter:
        logger.info(f"Filtering issuers by name containing: '{issuer_name_filter}'")

    found_cheaper = False
    competing_price = None
    total_competing_found = 0

    if all_expanded_contracts is None:
        # Load expanded contracts from cache or fetch if needed
        logger.info("No expanded contracts provided, loading from cache...")
        all_expanded_contracts = await fetch_and_expand_all_forge_contracts()

    if all_expanded_contracts and len(all_expanded_contracts) > 0:
        # Use pre-expanded contracts - much more efficient!
        logger.debug(f"Using pre-expanded contracts list with {len(all_expanded_contracts)} contracts")

        # Filter contracts for this region and basic criteria
        region_contracts = []
        for comp_contract in all_expanded_contracts:
            comp_start_location = comp_contract.get("start_location_id")
            if comp_start_location:
                comp_region_id = await get_region_from_location(comp_start_location)
                if comp_region_id == region_id:
                    region_contracts.append(comp_contract)

        logger.debug(f"Found {len(region_contracts)} contracts in region {region_id}")

        for comp_contract in region_contracts:
            comp_contract_id = comp_contract.get("contract_id")
            comp_price = comp_contract.get("price", 0)
            comp_issuer_id = comp_contract.get("issuer_id")
            comp_issuer_corp_id = comp_contract.get("issuer_corporation_id")
            comp_title = comp_contract.get("title", "")
            comp_items = comp_contract.get("items", [])

            # Debug: Log all contracts we're considering
            logger.debug(f"Evaluating contract {comp_contract_id}: type={comp_contract.get('type')}, status={comp_contract.get('status')}, price={comp_price}, issuer={comp_issuer_id}")

            # Quick filters that don't require API calls
            if comp_contract.get("type") != "item_exchange":
                logger.debug(f"Skipping contract {comp_contract_id}: not item_exchange")
                continue
            if comp_contract.get("status") != "outstanding":
                logger.debug(f"Skipping contract {comp_contract_id}: not outstanding")
                continue
            if comp_contract.get("contract_id") == contract_id:
                logger.debug(f"Skipping contract {comp_contract_id}: same contract")
                continue
            if comp_contract.get("issuer_id") == contract_issuer_id:
                logger.debug(f"Skipping contract {comp_contract_id}: same issuer")
                continue

            # If limiting to specific issuers, check that here
            if limit_to_issuer_ids and comp_issuer_id not in limit_to_issuer_ids:
                logger.debug(f"Skipping contract {comp_contract_id}: issuer {comp_issuer_id} not in allowed list {limit_to_issuer_ids}")
                continue

            # If filtering by issuer name, check names here
            if issuer_name_filter:
                issuer_name = comp_contract.get("issuer_name", "")
                corp_name = comp_contract.get("issuer_corporation_name", "")

                # Check if any of the names contain the filter text (case insensitive)
                name_matches = (
                    issuer_name_filter.lower() in issuer_name.lower() or
                    issuer_name_filter.lower() in corp_name.lower() or
                    issuer_name_filter.lower() in comp_title.lower()
                )

                if not name_matches:
                    logger.debug(f"Skipping contract {comp_contract_id}: name filter '{issuer_name_filter}' not found in '{issuer_name}'/'{corp_name}'/'{comp_title}'")
                    continue

                logger.debug(f"Contract {comp_contract_id} matches name filter: issuer='{issuer_name}', corp='{corp_name}', title='{comp_title}'")

            if comp_price <= 0:
                logger.debug(f"Skipping contract {comp_contract_id}: invalid price")
                continue

            # Use pre-expanded items data
            if not comp_items or len(comp_items) != 1:
                logger.debug(f"Skipping contract {comp_contract_id}: not single item or no items")
                continue

            comp_item = comp_items[0]
            comp_type_id = comp_item.get("type_id")
            comp_is_blueprint_copy = comp_item.get("is_blueprint_copy", False)
            comp_quantity = comp_item.get("quantity", 1)

            logger.debug(f"Contract {comp_contract_id} item: type_id={comp_type_id}, is_blueprint_copy={comp_is_blueprint_copy}, quantity={comp_quantity}")

            if (comp_type_id == type_id and
                comp_is_blueprint_copy == is_blueprint_copy):
                if comp_quantity > 0:
                    final_comp_price_per_item = comp_price / comp_quantity
                    total_competing_found += 1

                    logger.info(f"Found competing contract {comp_contract_id}: price_per_item={final_comp_price_per_item:.2f}, our_price={price_per_item:.2f}")

                    if final_comp_price_per_item < price_per_item:
                        logger.info(
                            f"Contract {contract_id} outbid by contract {comp_contract_id} with "
                            f"price_per_item: {final_comp_price_per_item:.2f}"
                        )
                        found_cheaper = True
                        competing_price = final_comp_price_per_item
                        break  # Found cheaper contract, can stop
                else:
                    logger.debug(f"Skipping contract {comp_contract_id}: invalid quantity")
            else:
                logger.debug(f"Skipping contract {comp_contract_id}: type_id mismatch ({comp_type_id} != {type_id}) or blueprint_copy mismatch ({comp_is_blueprint_copy} != {is_blueprint_copy})")

    else:
        # Fallback to original page-by-page approach
        logger.debug("No pre-expanded contracts provided, using page-by-page fetching")

        # OPTIMIZED APPROACH: Check first few pages with smart filtering
        max_pages_to_check = 5  # Check up to 5 pages (5000 contracts max)

        for page in range(1, max_pages_to_check + 1):
            try:
                # Fetch contracts for this page, sorted by price (cheapest first)
                contracts_page = await fetch_public_contracts_async(region_id, page, sort_by_price=True)
                if not contracts_page:
                    logger.debug(f"No contracts found on page {page} for region {region_id}")
                    break

                logger.debug(f"Fetched {len(contracts_page)} contracts from page {page} in region {region_id}")

                # Define reasonable price range to check (70% to 200% of our contract price)
                min_price = price_per_item * 0.7
                max_price = price_per_item * 2.0

                # Process contracts with smart filtering
                for contract in contracts_page:
                    comp_contract_id = contract.get("contract_id")
                    comp_price = contract.get("price", 0)
                    comp_volume = contract.get("volume", 1)
                    comp_issuer_id = contract.get("issuer_id")
                    comp_issuer_corp_id = contract.get("issuer_corporation_id")
                    comp_title = contract.get("title", "")

                    # Debug: Log all contracts we're considering
                    logger.debug(f"Evaluating contract {comp_contract_id}: type={contract.get('type')}, status={contract.get('status')}, price={comp_price}, issuer={comp_issuer_id}")

                    # Quick filters that don't require API calls
                    if contract.get("type") != "item_exchange":
                        logger.debug(f"Skipping contract {comp_contract_id}: not item_exchange")
                        continue
                    if contract.get("status") != "outstanding":
                        logger.debug(f"Skipping contract {comp_contract_id}: not outstanding")
                        continue
                    if contract.get("contract_id") == contract_id:
                        logger.debug(f"Skipping contract {comp_contract_id}: same contract")
                        continue
                    if contract.get("issuer_id") == contract_issuer_id:
                        logger.debug(f"Skipping contract {comp_contract_id}: same issuer")
                        continue

                    # If limiting to specific issuers, check that here
                    if limit_to_issuer_ids and comp_issuer_id not in limit_to_issuer_ids:
                        logger.debug(f"Skipping contract {comp_contract_id}: issuer {comp_issuer_id} not in allowed list {limit_to_issuer_ids}")
                        continue

                    # If filtering by issuer name, check names here
                    if issuer_name_filter:
                        issuer_names = await get_issuer_names([comp_issuer_id, comp_issuer_corp_id] if comp_issuer_corp_id else [comp_issuer_id])
                        issuer_name = issuer_names.get(comp_issuer_id, "")
                        corp_name = issuer_names.get(comp_issuer_corp_id, "") if comp_issuer_corp_id else ""

                        # Check if any of the names contain the filter text (case insensitive)
                        name_matches = (
                            issuer_name_filter.lower() in issuer_name.lower() or
                            issuer_name_filter.lower() in corp_name.lower() or
                            issuer_name_filter.lower() in comp_title.lower()
                        )

                        if not name_matches:
                            logger.debug(f"Skipping contract {comp_contract_id}: name filter '{issuer_name_filter}' not found in '{issuer_name}'/'{corp_name}'/'{comp_title}'")
                            continue

                        logger.debug(f"Contract {comp_contract_id} matches name filter: issuer='{issuer_name}', corp='{corp_name}', title='{comp_title}'")

                    if comp_price <= 0:
                        logger.debug(f"Skipping contract {comp_contract_id}: invalid price")
                        continue

                    if comp_volume <= 0:
                        logger.debug(f"Skipping contract {comp_contract_id}: invalid volume")
                        continue

                    estimated_price_per_item = comp_price / comp_volume

                    # Skip if obviously not competitive
                    if estimated_price_per_item < min_price or estimated_price_per_item > max_price:
                        logger.debug(f"Skipping contract {comp_contract_id}: price_per_item {estimated_price_per_item:.2f} outside range [{min_price:.2f}, {max_price:.2f}]")
                        continue

                    logger.debug(f"Contract {comp_contract_id} passed initial filters, fetching items...")

                    # Only fetch items for potentially competitive contracts
                    try:
                        comp_items = await fetch_public_contract_items_async(comp_contract_id)
                        if not comp_items:
                            logger.debug(f"Skipping contract {comp_contract_id}: no items")
                            continue

                        if len(comp_items) != 1:
                            logger.debug(f"Skipping contract {comp_contract_id}: {len(comp_items)} items (not single item)")
                            continue

                        comp_item = comp_items[0]
                        comp_type_id = comp_item.get("type_id")
                        comp_is_blueprint_copy = comp_item.get("is_blueprint_copy", False)
                        comp_quantity = comp_item.get("quantity", 1)

                        logger.debug(f"Contract {comp_contract_id} item: type_id={comp_type_id}, is_blueprint_copy={comp_is_blueprint_copy}, quantity={comp_quantity}")

                        if (comp_type_id == type_id and
                            comp_is_blueprint_copy == is_blueprint_copy):
                            if comp_quantity > 0:
                                final_comp_price_per_item = comp_price / comp_quantity
                                total_competing_found += 1

                                logger.info(f"Found competing contract {comp_contract_id}: price_per_item={final_comp_price_per_item:.2f}, our_price={price_per_item:.2f}")

                                if final_comp_price_per_item < price_per_item:
                                    logger.info(
                                        f"Contract {contract_id} outbid by contract {comp_contract_id} with "
                                        f"price_per_item: {final_comp_price_per_item:.2f}"
                                    )
                                    found_cheaper = True
                                    competing_price = final_comp_price_per_item
                                    break  # Found cheaper contract, can stop
                            else:
                                logger.debug(f"Skipping contract {comp_contract_id}: invalid quantity")
                        else:
                            logger.debug(f"Skipping contract {comp_contract_id}: type_id mismatch ({comp_type_id} != {type_id}) or blueprint_copy mismatch ({comp_is_blueprint_copy} != {is_blueprint_copy})")

                    except Exception as e:
                        logger.debug(f"Failed to fetch items for contract {comp_contract_id}: {e}")
                        continue

                if found_cheaper:
                    break  # Found cheaper contract, stop checking more pages

                # Check if there are more pages
                if len(contracts_page) < 1000:  # ESI returns max 1000 per page
                    break  # No more pages available

            except Exception as e:
                logger.error(f"Error fetching page {page} for region {region_id}: {e}")
                break

    if found_cheaper:
        return True, competing_price

    logger.info(f"No competing contracts found for contract {contract_id} (checked {total_competing_found} potential competitors)")
    return False, None


@validate_input_params(dict, list)
async def check_contract_competition_hybrid(
    contract_data: Dict[str, Any], contract_items: List[Dict[str, Any]], limit_to_issuer_ids: Optional[List[int]] = None, issuer_name_filter: Optional[str] = None, all_expanded_contracts: Optional[List[Dict[str, Any]]] = None
) -> Tuple[bool, Optional[float], Optional[Dict[str, float]]]:
    """Check if a sell contract has been outbid by cheaper competing contracts in the same region.

    This is a wrapper around check_contract_competition that maintains the same interface
    for backward compatibility, but only performs contract-to-contract comparison.

    Args:
        contract_data: Contract information dictionary from ESI
        contract_items: List of items in the contract
        limit_to_issuer_ids: Optional list of issuer IDs to limit competition search to
        issuer_name_filter: Optional text to filter issuers by name (checks issuer name, corp name, and title)
        all_expanded_contracts: Optional list of pre-expanded contracts with full details

    Returns:
        Tuple of (is_outbid: bool, competing_price: float or None, market_data: None)
        - is_outbid: True if a cheaper competing contract exists
        - competing_price: The price per item of the cheapest competing contract, or None
        - market_data: Always None (no market data returned)

    Note:
        Only checks single-item sell contracts (item_exchange type) with positive quantities.
    """
    # Only perform contract-to-contract comparison
    is_outbid, competing_price = await check_contract_competition(contract_data, contract_items, limit_to_issuer_ids, issuer_name_filter, all_expanded_contracts)
    return is_outbid, competing_price, None


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
    cache_file = "cache/region_cache.json"
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
    if location_id >= 1000000000000:  # Structure
        # For structures, we need to fetch structure info to get solar_system_id, then region
        try:
            async with sess.get(
                f"{ESI_BASE_URL}/universe/structures/{location_id}",
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                struct_data = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            struct_data = None

        if struct_data:
            solar_system_id = struct_data.get("solar_system_id")
            if solar_system_id:
                try:
                    async with sess.get(
                        f"{ESI_BASE_URL}/universe/systems/{solar_system_id}",
                        headers={"Accept": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        response.raise_for_status()
                        system_data = await response.json()
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    system_data = None

                if system_data:
                    constellation_id = system_data.get("constellation_id")
                    if constellation_id:
                        try:
                            async with sess.get(
                                f"{ESI_BASE_URL}/universe/constellations/{constellation_id}",
                                headers={"Accept": "application/json"},
                                timeout=aiohttp.ClientTimeout(total=30),
                            ) as response:
                                response.raise_for_status()
                                constellation_data = await response.json()
                        except (aiohttp.ClientError, asyncio.TimeoutError):
                            constellation_data = None

                        if constellation_data:
                            region_id = constellation_data.get("region_id")
    else:  # Station
        try:
            async with sess.get(
                f"{ESI_BASE_URL}/universe/stations/{location_id}",
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                station_data = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            station_data = None

        if station_data:
            system_id = station_data.get("system_id")
            if system_id:
                try:
                    async with sess.get(
                        f"{ESI_BASE_URL}/universe/systems/{system_id}",
                        headers={"Accept": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        response.raise_for_status()
                        system_data = await response.json()
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    system_data = None

                if system_data:
                    constellation_id = system_data.get("constellation_id")
                    if constellation_id:
                        try:
                            async with sess.get(
                                f"{ESI_BASE_URL}/universe/constellations/{constellation_id}",
                                headers={"Accept": "application/json"},
                                timeout=aiohttp.ClientTimeout(total=30),
                            ) as response:
                                response.raise_for_status()
                                constellation_data = await response.json()
                        except (aiohttp.ClientError, asyncio.TimeoutError):
                            constellation_data = None

                        if constellation_data:
                            region_id = constellation_data.get("region_id")

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
        batch_ids = unique_ids[i:i + batch_size]

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


@validate_input_params(dict, bool, (int, type(None)), (list, type(None)), (dict, type(None)))
async def generate_contract_title(
    contract_data: Dict[str, Any],
    for_corp: bool = False,
    entity_id: Optional[int] = None,
    contract_items: Optional[List[Dict[str, Any]]] = None,
    blueprint_cache: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a descriptive contract title based on contract type and items.

    Creates human-readable titles that include item names, quantities, and contract details.
    Special handling for blueprint contracts and mixed item types.

    Args:
        contract_data: Contract information dictionary from ESI
        for_corp: Whether this is a corporation contract (affects title prefix)
        entity_id: Character or corporation ID (for context)
        contract_items: List of items in the contract (optional)
        blueprint_cache: Cached blueprint names (loaded automatically if not provided)

    Returns:
        Formatted contract title string

    Note:
        Titles follow the format: "[Corp] Item Name - Contract ID" for blueprints,
        or "[Corp] X Items (xQuantity) - Contract ID" for regular items.
    """
    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()

    blueprint_type_cache = load_blueprint_type_cache()

    contract_id = contract_data.get("contract_id")
    contract_type = contract_data.get("type", "unknown")
    status = contract_data.get("status", "unknown").title()

    # If no items, use default format
    if not contract_items:
        type_names = {"item_exchange": "Item Exchange", "auction": "Auction", "courier": "Courier", "loan": "Loan"}
        type_name = type_names.get(contract_type, contract_type.title())
        title = f"Contract {contract_id} - {type_name} ({status})"
    else:
        # If we have items, create a more descriptive title
        if len(contract_items) == 1:
            # Single item contract
            item = contract_items[0]
            type_id = item.get("type_id")
            quantity = item.get("quantity", 1)

            if type_id:
                # Get item name
                item_name = get_cached_blueprint_name(str(type_id))
                if item_name is None:
                    type_data = await fetch_public_esi(f"/universe/types/{type_id}")
                    if type_data:
                        item_name = type_data.get("name", f"Item {type_id}")
                        # Only cache if it's actually a blueprint
                        if "Blueprint" in item_name:
                            cleaned_name = item_name.replace(" Blueprint", "").strip()
                            blueprint_cache[str(type_id)] = cleaned_name
                            save_blueprint_cache(blueprint_cache)
                    else:
                        item_name = f"Item {type_id}"

                # Check if it's a blueprint (quantity -1 indicates BPO, or check if it's in blueprint cache)
                is_blueprint = str(type_id) in blueprint_type_cache and blueprint_type_cache[str(type_id)]
                if not is_blueprint:
                    # Double-check with ESI
                    type_data = await fetch_public_esi(f"/universe/types/{type_id}")
                    is_blueprint = type_data and "Blueprint" in type_data.get("name", "")

                if is_blueprint:
                    title = f"{item_name} - Contract {contract_id}"
                else:
                    # Regular item
                    title = f"{item_name} (x{quantity}) - Contract {contract_id}"

        else:
            # Multiple items contract - count blueprints and total quantity in single pass
            blueprint_count = 0
            total_quantity = 0

            for item in contract_items:
                quantity = item.get("quantity", 1)
                total_quantity += abs(quantity)  # Use abs in case of BPOs

                # Check if it's a blueprint
                type_id = item.get("type_id")
                if type_id:
                    # First check if it's in blueprint cache
                    if str(type_id) in blueprint_type_cache and blueprint_type_cache[str(type_id)]:
                        blueprint_count += 1
                    else:
                        # Check with ESI
                        type_data = await fetch_public_esi(f"/universe/types/{type_id}")
                        if type_data and "Blueprint" in type_data.get("name", ""):
                            blueprint_count += 1

            if blueprint_count == len(contract_items):
                # All items are blueprints
                title = f"{blueprint_count} Blueprints - Contract {contract_id}"
            elif blueprint_count > 0:
                # Mix of blueprints and other items
                title = (f"{blueprint_count} Blueprints + "
                         f"{len(contract_items) - blueprint_count} Items - Contract {contract_id}")
            else:
                # No blueprints, just regular items
                title = f"{len(contract_items)} Items (x{total_quantity}) - Contract {contract_id}"

    if for_corp:
        title = f"[Corp] {title}"

    return title


@validate_input_params(int, dict, bool, (int, type(None)), (str, type(None)), (dict, type(None)), (list, type(None)))
async def update_contract_in_wp(
    contract_id: int,
    contract_data: Dict[str, Any],
    for_corp: bool = False,
    entity_id: Optional[int] = None,
    access_token: Optional[str] = None,
    blueprint_cache: Optional[Dict[str, Any]] = None,
    all_expanded_contracts: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Update or create a contract post in WordPress with comprehensive metadata.

    Creates or updates WordPress posts for EVE contracts, including market competition
    analysis for sell orders. Only processes contracts containing blueprints.

    Args:
        contract_id: The EVE contract ID
        contract_data: Contract information dictionary from ESI
        for_corp: Whether this is a corporation contract
        entity_id: Character or corporation ID that has access to the contract
        access_token: Valid ESI access token for fetching contract items
        blueprint_cache: Cached blueprint names (loaded automatically if not provided)
        all_expanded_contracts: Optional list of pre-expanded contracts for competition analysis

    Returns:
        None

    Note:
        - Only creates posts for contracts containing blueprints
        - Performs market competition analysis for outstanding sell contracts
        - Updates existing posts only if data has changed
        - Includes contract items, pricing, and location metadata
    """
    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()

    blueprint_type_cache = load_blueprint_type_cache()

    slug = f"contract-{contract_id}"
    # Check if post exists by slug
    existing_posts = await wp_request("GET", f"/wp/v2/eve_contract?slug={slug}")
    existing_post = existing_posts[0] if existing_posts else None

    # Fetch contract items if we have access token
    contract_items = None
    if access_token:
        if for_corp and entity_id:
            contract_items = await fetch_corporation_contract_items(entity_id, contract_id, access_token)
        elif not for_corp and entity_id:
            contract_items = await fetch_character_contract_items(entity_id, contract_id, access_token)

    # Get region ID from start location
    region_id = None
    start_location_id = contract_data.get("start_location_id")
    if start_location_id:
        region_id = await get_region_from_location(start_location_id)

    # Check if contract contains blueprints - only track contracts with blueprints
    has_blueprint = False
    if contract_items:
        for item in contract_items:
            type_id = item.get("type_id")
            if type_id and str(type_id) in blueprint_type_cache and blueprint_type_cache[str(type_id)]:
                has_blueprint = True
                break

    if not has_blueprint:
        logger.info(f"Contract {contract_id} contains no blueprints, skipping")
        return

    title = await generate_contract_title(
        contract_data,
        for_corp=for_corp,
        entity_id=entity_id,
        contract_items=contract_items,
        blueprint_cache=blueprint_cache,
    )

    post_data = {
        "title": title,
        "slug": slug,
        "status": "publish",
        "meta": {
            "_eve_contract_id": str(contract_id),
            "_eve_contract_type": contract_data.get("type"),
            "_eve_contract_status": contract_data.get("status"),
            "_eve_contract_issuer_id": str(contract_data.get("issuer_id"))
            if contract_data.get("issuer_id") is not None
            else None,
            "_eve_contract_issuer_corp_id": str(contract_data.get("issuer_corporation_id"))
            if contract_data.get("issuer_corporation_id") is not None
            else None,
            "_eve_contract_assignee_id": str(contract_data.get("assignee_id"))
            if contract_data.get("assignee_id")
            else None,
            "_eve_contract_acceptor_id": str(contract_data.get("acceptor_id"))
            if contract_data.get("acceptor_id")
            else None,
            "_eve_contract_start_location_id": str(contract_data.get("start_location_id"))
            if contract_data.get("start_location_id")
            else None,
            "_eve_contract_end_location_id": str(contract_data.get("end_location_id"))
            if contract_data.get("end_location_id")
            else None,
            "_eve_contract_region_id": str(region_id) if region_id else None,
            "_eve_contract_date_issued": contract_data.get("date_issued"),
            "_eve_contract_date_expired": contract_data.get("date_expired"),
            "_eve_contract_date_accepted": contract_data.get("date_accepted"),
            "_eve_contract_date_completed": contract_data.get("date_completed"),
            "_eve_contract_price": str(contract_data.get("price")) if contract_data.get("price") is not None else None,
            "_eve_contract_reward": str(contract_data.get("reward"))
            if contract_data.get("reward") is not None
            else None,
            "_eve_contract_collateral": str(contract_data.get("collateral"))
            if contract_data.get("collateral") is not None
            else None,
            "_eve_contract_buyout": str(contract_data.get("buyout"))
            if contract_data.get("buyout") is not None
            else None,
            "_eve_contract_volume": str(contract_data.get("volume"))
            if contract_data.get("volume") is not None
            else None,
            "_eve_contract_days_to_complete": str(contract_data.get("days_to_complete"))
            if contract_data.get("days_to_complete") is not None
            else None,
            "_eve_contract_title": contract_data.get("title"),
            "_eve_contract_for_corp": str(for_corp).lower(),
            "_eve_contract_entity_id": str(entity_id),
            "_eve_last_updated": datetime.now(timezone.utc).isoformat(),
        },
    }

    # Remove null values from meta to avoid WordPress validation errors
    post_data["meta"] = {k: v for k, v in post_data["meta"].items() if v is not None}

    # Add items data if available
    if contract_items:
        post_data["meta"]["_eve_contract_items"] = json.dumps(contract_items)

        # Store item types for easier querying
        item_types = [str(item.get("type_id")) for item in contract_items if item.get("type_id")]
        post_data["meta"]["_eve_contract_item_types"] = ",".join(item_types)

        # Check for market competition on outstanding sell contracts
        if contract_data.get("status") == "outstanding" and contract_data.get("type") == "item_exchange":
            is_outbid, competing_price = await check_contract_competition(contract_data, contract_items, all_expanded_contracts=all_expanded_contracts)
            if is_outbid:
                post_data["meta"]["_eve_contract_outbid"] = "1"
                post_data["meta"]["_eve_contract_competing_price"] = str(competing_price)
                logger.warning(f"Contract {contract_id} is outbid by contract price: {competing_price}")
            else:
                post_data["meta"]["_eve_contract_outbid"] = "0"
                if "_eve_contract_competing_price" in post_data["meta"]:
                    del post_data["meta"]["_eve_contract_competing_price"]
        else:
            # Not a sell contract or not outstanding - ensure outbid is false
            post_data["meta"]["_eve_contract_outbid"] = "0"
            if "_eve_contract_competing_price" in post_data["meta"]:
                del post_data["meta"]["_eve_contract_competing_price"]
    else:
        # No contract items - ensure outbid is set to false
        post_data["meta"]["_eve_contract_outbid"] = "0"
        if "_eve_contract_competing_price" in post_data["meta"]:
            del post_data["meta"]["_eve_contract_competing_price"]

    if existing_post:
        existing_meta = existing_post.get("meta", {})
        # Send alert if this is newly outbid
        was_outbid = existing_meta.get("_eve_contract_outbid") == "1"
        if not was_outbid and post_data["meta"].get("_eve_contract_outbid") == "1":
            price = post_data['meta'].get('_eve_contract_competing_price', 'unknown')
            logger.warning(f"Contract {contract_id} is newly outbid by contract price: {price}")
        # Check if title changed before updating
        existing_title = existing_post.get("title", {}).get("rendered", "")

        # Compare key fields to see if update is needed
        needs_update = (
            existing_title != title
            or str(existing_meta.get("_eve_contract_status", "")) != str(contract_data.get("status", ""))
            or str(existing_meta.get("_eve_contract_items", ""))
            != str(json.dumps(contract_items) if contract_items else "")
            or str(existing_meta.get("_eve_contract_outbid", "0"))
            != str(post_data["meta"].get("_eve_contract_outbid", "0"))
        )

        if not needs_update:
            logger.info(f"Contract {contract_id} unchanged, skipping update")
            return

        # Update existing
        post_id = existing_post["id"]
        result = await wp_request("PUT", f"/wp/v2/eve_contract/{post_id}", post_data)
    else:
        # Create new (without region_id to avoid ACF protection issues)
        # Add thumbnail from first contract item
        if contract_items and len(contract_items) > 0:
            first_item_type_id = contract_items[0].get("type_id")
            if first_item_type_id:
                image_url = await fetch_type_icon(first_item_type_id, size=512)
                post_data["meta"]["_thumbnail_external_url"] = image_url
        result = await wp_request("POST", "/wp/v2/eve_contract", post_data)

    if result:
        logger.info(f"Updated contract: {contract_id} - {title}")
    else:
        logger.error(f"Failed to update contract {contract_id}")


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


@validate_input_params(int, str, str, dict, dict, dict, dict, dict)
async def process_character_contracts(
    char_id: int,
    access_token: str,
    char_name: str,
    wp_post_id_cache: Dict[str, Any],
    blueprint_cache: Dict[str, Any],
    location_cache: Dict[str, Any],
    structure_cache: Dict[str, Any],
    failed_structures: Dict[str, Any],
) -> None:
    """
    Process contracts for a character.

    Fetches character contracts, processes blueprints from contract items,
    and creates/updates contract posts in WordPress.

    Args:
        char_id: Character ID to process contracts for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    char_contracts = await fetch_character_contracts(char_id, access_token)
    if char_contracts:
        logger.info(f"Character contracts for {char_name}: {len(char_contracts)} items")

        # Process blueprints from contracts
        contract_blueprints = await extract_blueprints_from_contracts(char_contracts, "char", char_id)
        if contract_blueprints:
            logger.info(f"Character contract blueprints: {len(contract_blueprints)} items")
            # Process blueprints in parallel
            await process_blueprints_parallel(
                contract_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures,
            )

        # Fetch and expand all Forge contracts once for competition checking
        logger.info("Fetching all expanded contracts from The Forge region for competition analysis...")
        all_expanded_contracts = await fetch_and_expand_all_forge_contracts()

        # Process contracts themselves
        for contract in char_contracts:
            contract_status = contract.get("status", "")
            if contract_status in ["finished", "deleted"]:
                # Skip finished/deleted contracts to improve performance
                continue
            elif contract_status == "expired":
                logger.info(f"EXPIRED CHARACTER CONTRACT TO DELETE MANUALLY: {contract['contract_id']}")
            await update_contract_in_wp(
                contract["contract_id"],
                contract,
                for_corp=False,
                entity_id=char_id,
                access_token=access_token,
                blueprint_cache=blueprint_cache,
                all_expanded_contracts=all_expanded_contracts,
            )


async def fetch_and_expand_all_forge_contracts() -> List[Dict[str, Any]]:
    """Fetch all outstanding contracts from The Forge region and expand with full details."""
    logger.info("Fetching and expanding all outstanding contracts from The Forge region...")

    cache_file = os.path.join(CACHE_DIR, "all_contracts_forge.json")

    # Try to load from cache first
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cached_contracts = json.load(f)
            if cached_contracts and len(cached_contracts) > 0:
                # Check if contracts are already expanded (have issuer_name field)
                if cached_contracts[0].get('issuer_name'):
                    logger.info(f"Loaded {len(cached_contracts)} expanded contracts from cache")
                    return cached_contracts
                else:
                    logger.info(f"Loaded {len(cached_contracts)} basic contracts from cache, expanding...")
                    # Contracts need expansion
                    expanded_contracts = await expand_all_contracts(cached_contracts)
                    # Save expanded version back to cache
                    with open(cache_file, 'w') as f:
                        json.dump(expanded_contracts, f, indent=2, default=str)
                    logger.info(f"Saved {len(expanded_contracts)} expanded contracts to cache")
                    return expanded_contracts
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load cached contracts: {e}")

    # Cache is empty or doesn't exist, fetch fresh data
    logger.info("Cache empty or invalid, fetching fresh contract data...")

    # Fetch all contracts from The Forge
    contracts = await fetch_all_contracts_in_region(FORGE_REGION_ID)
    logger.info(f"fetch_all_contracts_in_region returned {len(contracts)} contracts")

    # Filter for outstanding contracts only
    # Note: Public contracts endpoint only returns active contracts, so all are effectively outstanding
    outstanding_contracts = contracts  # All contracts from public endpoint are active
    logger.info(f"Found {len(outstanding_contracts)} active contracts from public endpoint")

    # Expand all contracts with full details
    expanded_contracts = await expand_all_contracts(outstanding_contracts)
    logger.info(f"expand_all_contracts returned {len(expanded_contracts)} contracts")

    # Save to cache file
    with open(cache_file, 'w') as f:
        json.dump(expanded_contracts, f, indent=2, default=str)
    logger.info(f"Saved {len(expanded_contracts)} expanded contracts to {cache_file}")

    return expanded_contracts


async def get_user_contracts(char_id: int, access_token: str) -> List[Dict[str, Any]]:
    from esi_oauth import load_tokens, save_tokens
    from datetime import datetime, timezone

    # Get corporation contracts for the character
    try:
        # Get corporation ID
        char_data = await fetch_public_esi(f"/characters/{char_id}/")
        if not char_data or 'corporation_id' not in char_data:
            logger.warning("Could not get corporation ID")
            return []

        corp_id = char_data['corporation_id']
        logger.info(f"Fetching corporation contracts for corp ID: {corp_id}")

        corp_contracts = await fetch_corporation_contracts(corp_id, access_token)
        if not corp_contracts:
            logger.warning("No corporation contracts found")
            return []

        # Filter for outstanding item_exchange contracts
        outstanding_item_exchange = [
            c for c in corp_contracts
            if c.get("status") == "outstanding" and c.get("type") == "item_exchange"
        ]

        user_contracts = []

        for contract in outstanding_item_exchange:
            contract_id = contract["contract_id"]

            # Get contract items
            contract_items = await fetch_corporation_contract_items(corp_id, contract_id, access_token)

            if not contract_items:
                continue

            # Get item details
            items_details = []
            for item in contract_items:
                type_id = item.get("type_id")
                if type_id:
                    type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
                    item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"
                    items_details.append({
                        "type_id": type_id,
                        "name": item_name,
                        "quantity": item.get("quantity", 1),
                        "is_blueprint_copy": item.get("is_blueprint_copy", False)
                    })

            user_contract = {
                'contract_id': contract_id,
                'type': contract.get("type"),
                'price': contract.get("price", 0),
                'title': contract.get("title", ""),
                'items': items_details,
                'item_count': len(contract_items)
            }

            user_contracts.append(user_contract)

        logger.info(f"Found {len(user_contracts)} user outstanding contracts")
        return user_contracts

    except Exception as e:
        logger.error(f"Error fetching user contracts: {e}")
        return []


async def expand_all_contracts(contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Expand all contracts with issuer names and item details including blueprint attributes."""
    logger.info(f"expand_all_contracts called with {len(contracts)} contracts")

    # Initialize cache manager
    cache_manager = ContractCacheManager()

    # Get all unique issuer IDs first
    issuer_ids = set()
    for contract in contracts:
        if contract.get("issuer_id"):
            issuer_ids.add(contract["issuer_id"])
        if contract.get("issuer_corporation_id"):
            issuer_ids.add(contract["issuer_corporation_id"])

    logger.info(f"Found {len(issuer_ids)} unique issuer IDs")

    # Load existing issuer cache and get missing names
    issuer_cache = await cache_manager.load_issuer_cache()
    missing_issuers = await cache_manager.get_missing_issuer_names(list(issuer_ids), issuer_cache)
    if missing_issuers:
        issuer_cache.update(missing_issuers)
        await cache_manager.save_issuer_cache(issuer_cache)

    logger.info(f"Issuer cache: {len(issuer_cache)} total entries")

    # Load existing caches
    issuer_cache = await cache_manager.load_issuer_cache()
    type_cache = await cache_manager.load_type_cache()
    contract_items_cache = await cache_manager.load_contract_items_cache()

    logger.info(f"Issuer cache: {len(issuer_cache)} total entries")
    logger.info(f"Type cache: {len(type_cache)} total entries")
    logger.info(f"Contract items cache: {len(contract_items_cache)} total entries")

    # Process contracts in batches to avoid memory issues and provide progress
    batch_size = 1000
    expanded_contracts = []
    logger.info(f"Processing contracts in batches of {batch_size}...")

    for batch_start in range(0, len(contracts), batch_size):
        batch_end = min(batch_start + batch_size, len(contracts))
        batch_contracts = contracts[batch_start:batch_end]

        logger.info(f"Processing batch {batch_start//batch_size + 1}: contracts {batch_start} to {batch_end-1}")

        # First, add contracts with issuer names only
        for contract in batch_contracts:
            contract_id = contract["contract_id"]
            issuer_id = contract.get("issuer_id")
            issuer_corp_id = contract.get("issuer_corporation_id")

            expanded = contract.copy()
            expanded["issuer_name"] = issuer_cache.get(str(issuer_id), "Unknown")
            expanded["issuer_corporation_name"] = issuer_cache.get(str(issuer_corp_id), "Unknown") if issuer_corp_id else "Unknown"
            # Items will be added later

            expanded_contracts.append(expanded)

        logger.info(f"Completed batch {batch_start//batch_size + 1}, total expanded: {len(expanded_contracts)}")

    logger.info(f"All contracts expanded with issuer names. Now adding item details...")

    # Second pass: add item details in very small batches
    item_batch_size = 20  # Very small batches for item fetching
    for batch_start in range(0, len(expanded_contracts), item_batch_size):
        batch_end = min(batch_start + item_batch_size, len(expanded_contracts))
        logger.info(f"Adding items to batch {batch_start//item_batch_size + 1}: contracts {batch_start} to {batch_end-1}")

        # Collect type IDs needed for this small batch
        batch_type_ids = set()
        contracts_to_update = []

        for i in range(batch_start, batch_end):
            contract = expanded_contracts[i]
            if contract.get("type") == "item_exchange":
                contracts_to_update.append(i)
                contract_id = contract["contract_id"]

                try:
                    contract_id_str = str(contract_id)
                    contract_items = contract_items_cache.get(contract_id_str)
                    if contract_items is None:
                        contract_items = await fetch_public_contract_items_async(contract_id)
                        if contract_items:
                            contract_items_cache[contract_id_str] = contract_items
                            await cache_manager.save_contract_items_cache(contract_items_cache)
                    if contract_items:
                        for item in contract_items:
                            type_id = item.get("type_id")
                            if type_id and str(type_id) not in type_cache:
                                batch_type_ids.add(type_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch items for contract {contract_id}: {e}")

        # Fetch missing type data for this batch
        if batch_type_ids:
            logger.info(f"Fetching {len(batch_type_ids)} missing type IDs...")
            missing_types = await cache_manager.get_missing_type_data(list(batch_type_ids), type_cache)
            if missing_types:
                type_cache.update(missing_types)
                await cache_manager.save_type_cache(type_cache)

        # Add item details to contracts in this batch
        for i in contracts_to_update:
            contract = expanded_contracts[i]
            contract_id = contract["contract_id"]

            try:
                contract_id_str = str(contract_id)
                contract_items = contract_items_cache.get(contract_id_str)
                if contract_items is None:
                    contract_items = await fetch_public_contract_items_async(contract_id)
                    if contract_items:
                        contract_items_cache[contract_id_str] = contract_items
                        await cache_manager.save_contract_items_cache(contract_items_cache)
                if contract_items:
                    items_details = []
                    for item in contract_items:
                        type_id = item.get("type_id")
                        if type_id:
                            # Use cached type data
                            type_data = type_cache.get(str(type_id))
                            item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"

                            item_detail = {
                                "type_id": type_id,
                                "name": item_name,
                                "quantity": item.get("quantity", 1),
                                "is_blueprint_copy": item.get("is_blueprint_copy", False)
                            }

                            # Determine if BPO or BPC and get blueprint attributes
                            if item_detail["is_blueprint_copy"]:
                                item_detail["blueprint_type"] = "BPC"
                                # For BPCs, get the blueprint attributes
                                if "time_efficiency" in item and "material_efficiency" in item:
                                    item_detail["time_efficiency"] = item.get("time_efficiency", 0)
                                    item_detail["material_efficiency"] = item.get("material_efficiency", 0)
                            else:
                                # Check if this is a blueprint original by looking at the type data
                                group_id = type_data.get("group_id") if type_data else None
                                if group_id == 2:  # Blueprint group
                                    item_detail["blueprint_type"] = "BPO"
                                    # BPOs don't have efficiency attributes in contract items
                                    item_detail["time_efficiency"] = None
                                    item_detail["material_efficiency"] = None
                                else:
                                    item_detail["blueprint_type"] = None

                            items_details.append(item_detail)

                    expanded_contracts[i]["items"] = items_details
                    expanded_contracts[i]["item_count"] = len(contract_items)
            except Exception as e:
                logger.warning(f"Failed to process items for contract {contract_id}: {e}")

    logger.info(f"Expanded {len(expanded_contracts)} contracts total")
    return expanded_contracts


def load_tokens():
    """Load stored tokens."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return {}


async def fetch_all_contracts_in_region(region_id: int) -> List[Dict[str, Any]]:
    """Fetch all contracts from a region."""
    logger.info(f"Fetching all contracts from region {region_id}")

    all_contracts = []
    page = 1

    while True:
        logger.info(f"Fetching page {page}...")
        contracts = await fetch_public_contracts_async(region_id, page=page)

        if not contracts:
            logger.info(f"No more contracts on page {page}, stopping")
            break

        logger.info(f"Found {len(contracts)} contracts on page {page}")

        # Debug: print types of first 5 contracts
        if page == 1:
            for i, c in enumerate(contracts[:5]):
                logger.info(f"Contract {i}: type={c.get('type')}, status={c.get('status')}, price={c.get('price')}")

        # Store all contracts
        for contract in contracts:
            contract_id = contract["contract_id"]
            contract_type = contract.get("type")

            contract_data = {
                'contract_id': contract_id,
                'type': contract_type,
                'price': contract.get("price", 0),
                'issuer_id': contract.get("issuer_id"),
                'issuer_corporation_id': contract.get("issuer_corporation_id"),
                'start_location_id': contract.get("start_location_id"),
                'title': contract.get("title", ""),
                'date_issued': contract.get("date_issued"),
                'date_expired': contract.get("date_expired"),
                'volume': contract.get("volume", 1),
                'status': 'outstanding',  # Public endpoint only returns active contracts
            }

            all_contracts.append(contract_data)
            logger.debug(f"Stored contract {contract_id} of type {contract_type}")

        page += 1

        # Safety limit
        if page > 10:  # Limit to 10 pages for now
            logger.warning("Reached page limit of 10, stopping")
            break

    logger.info(f"Total contracts found: {len(all_contracts)}")
    return all_contracts


def save_bpo_contracts(contracts: List[Dict[str, Any]], filename: str):
    """Save BPO contracts to JSON file."""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        json.dump(contracts, f, indent=2, default=str)
    logger.info(f"Saved {len(contracts)} BPO contracts to {filename}")


async def filter_single_bpo_contracts(contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter contracts to only single BPO contracts."""
    logger.info("Filtering for single BPO contracts...")
    single_bpo_contracts = []

    for contract in contracts:
        if contract.get("type") != "item_exchange":
            continue

        contract_id = contract["contract_id"]

        # Fetch items
        contract_items = await fetch_public_contract_items_async(contract_id)
        if not contract_items or len(contract_items) != 1:
            continue

        item = contract_items[0]
        type_id = item.get("type_id")
        quantity = item.get("quantity", 1)
        is_blueprint_copy = item.get("is_blueprint_copy", False)

        if quantity == -1 and not is_blueprint_copy and type_id:
            # Get item name
            type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
            item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"

            bpo_contract = contract.copy()
            bpo_contract.update({
                'type_id': type_id,
                'item_name': item_name,
                'contract_items': contract_items
            })

            single_bpo_contracts.append(bpo_contract)
            logger.debug(f"Found single BPO contract {contract_id}: {item_name}")

    logger.info(f"Found {len(single_bpo_contracts)} single BPO contracts")
    return single_bpo_contracts


async def get_user_single_bpo_contracts() -> List[Dict[str, Any]]:
    """Get user's outstanding single BPO contracts."""
    from esi_oauth import load_tokens, save_tokens
    from datetime import datetime, timezone

    tokens = load_tokens()
    if not tokens:
        logger.warning("No tokens found")
        return []

    # Find Dr FiLiN's token
    dr_filin_token = None
    dr_filin_char_id = None
    for char_id, token_data in tokens.items():
        if token_data.get("name", "").lower() == "dr filin":
            dr_filin_token = token_data
            dr_filin_char_id = int(char_id)
            break

    if not dr_filin_token:
        logger.warning("Dr FiLiN's token not found")
        return []

    # Check if token is expired and refresh if needed
    try:
        expired = datetime.now(timezone.utc) > datetime.fromisoformat(
            dr_filin_token.get("expires_at", "2000-01-01T00:00:00+00:00")
        )
    except (ValueError, TypeError):
        expired = True

    if expired:
        logger.info("Dr FiLiN's token expired, refreshing...")
        from api_client import refresh_token
        new_token = refresh_token(dr_filin_token["refresh_token"])
        if new_token:
            dr_filin_token.update(new_token)
            save_tokens(tokens)
            logger.info("Token refreshed successfully")
        else:
            logger.warning("Failed to refresh token")
            return []

    access_token = dr_filin_token["access_token"]

    # Fetch corporation contracts
    try:
        # Get corporation ID
        char_data = await fetch_public_esi(f"/characters/{dr_filin_char_id}/")
        if not char_data or 'corporation_id' not in char_data:
            logger.warning("Could not get corporation ID")
            return []

        corp_id = char_data['corporation_id']
        logger.info(f"Fetching corporation contracts for corp ID: {corp_id}")

        corp_contracts = await fetch_corporation_contracts(corp_id, access_token)
        if not corp_contracts:
            logger.warning("No corporation contracts found")
            return []

        # Filter for outstanding item_exchange contracts
        outstanding_item_exchange = [
            c for c in corp_contracts
            if c.get("status") == "outstanding" and c.get("type") == "item_exchange"
        ]

        user_bpo_contracts = []

        for contract in outstanding_item_exchange:
            contract_id = contract["contract_id"]

            # Get contract items
            contract_items = await fetch_corporation_contract_items(corp_id, contract_id, access_token)

            if not contract_items or len(contract_items) != 1:
                continue

            item = contract_items[0]
            type_id = item.get("type_id")
            quantity = item.get("quantity", 1)
            is_blueprint_copy = item.get("is_blueprint_copy", False)

            if quantity == -1 and not is_blueprint_copy and type_id:
                # Get item name
                type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
                item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"

                user_contract = {
                    'contract_id': contract_id,
                    'type_id': type_id,
                    'item_name': item_name,
                    'price': contract.get("price", 0),
                    'contract_data': contract,
                    'contract_items': contract_items
                }

                user_bpo_contracts.append(user_contract)

        logger.info(f"Found {len(user_bpo_contracts)} user single BPO contracts")
        return user_bpo_contracts

    except Exception as e:
        logger.error(f"Error fetching user contracts: {e}")
        return []


def compare_contracts(user_contracts: List[Dict[str, Any]], market_contracts: List[Dict[str, Any]]):
    """Compare user's contracts to market contracts to find cheaper alternatives."""
    logger.info("Comparing user contracts to market contracts...")

    for user_contract in user_contracts:
        user_type_id = user_contract['type_id']
        user_price = user_contract['price']
        user_contract_id = user_contract['contract_id']
        item_name = user_contract['item_name']

        # Find market contracts for the same BPO
        matching_market = [
            c for c in market_contracts
            if c['type_id'] == user_type_id and c['contract_id'] != user_contract_id
        ]

        if not matching_market:
            logger.info(f"No market contracts found for {item_name} (contract {user_contract_id})")
            continue

        # Sort by price ascending
        matching_market.sort(key=lambda x: x['price'])

        cheapest_market = matching_market[0]
        cheapest_price = cheapest_market['price']

        if cheapest_price < user_price:
            price_diff = user_price - cheapest_price
            logger.warning(f"CHEAPER FOUND for {item_name}:")
            logger.warning(f"  Your contract {user_contract_id}: {user_price:,.2f} ISK")
            logger.warning(f"  Market contract {cheapest_market['contract_id']}: {cheapest_price:,.2f} ISK")
            logger.warning(f"  Price difference: {price_diff:,.2f} ISK")
            logger.warning(f"  Market issuer: {cheapest_market.get('issuer_id', 'Unknown')}")
            logger.warning(f"  Market title: {cheapest_market.get('title', 'N/A')}")
            logger.warning("")
        else:
            logger.info(f"Your contract {user_contract_id} for {item_name} is the cheapest at {user_price:,.2f} ISK")


@validate_input_params(set, set)
async def cleanup_contract_posts(allowed_corp_ids: set, allowed_issuer_ids: set) -> None:
    """
    Clean up contract posts that don't match filtering criteria.

    Removes contract posts from unauthorized issuers or with finished/deleted status.
    Lists expired contracts for manual deletion to preserve private contract visibility.

    Args:
        allowed_corp_ids: Set of corporation IDs allowed for contract processing.
        allowed_issuer_ids: Set of character IDs allowed as contract issuers.

    Note:
        Preserves private contracts that may still be visible to authorized characters.
        Only removes contracts from unauthorized sources or completed contracts.
    """
    logger.info("Cleaning up contract posts...")

    contracts = await wp_request("GET", "/wp/v2/eve_contract", {"per_page": WP_PER_PAGE})
    if contracts:
        for contract in contracts:
            meta = contract.get("meta", {})
            status = meta.get("_eve_contract_status")
            issuer_corp_id = meta.get("_eve_contract_issuer_corp_id")
            issuer_id = meta.get("_eve_contract_issuer_id")
            contract_id = meta.get("_eve_contract_id")

            should_delete = False
            # Don't delete private contracts - they may still be visible to authorized characters
            # Only delete contracts from unauthorized issuers or finished/deleted contracts
            if status in ["finished", "deleted"]:
                should_delete = True
                logger.info(f"Deleting {status} contract: {contract_id}")
            elif (
                issuer_corp_id
                and int(issuer_corp_id) not in allowed_corp_ids
                and issuer_id
                and int(issuer_id) not in allowed_issuer_ids
            ):
                should_delete = True
                logger.info(f"Deleting contract from unauthorized issuer: {contract_id}")
            elif status == "expired":
                # List expired contracts for manual deletion
                title = contract.get("title", {}).get("rendered", f"Contract {contract_id}")
                logger.info(f"EXPIRED CONTRACT TO DELETE MANUALLY: {title} (ID: {contract_id})")

            if should_delete:
                result = await wp_request("DELETE", f"/wp/v2/eve_contract/{contract['id']}", {"force": True})
                if result:
                    logger.info(f"Deleted contract: {contract_id}")
                else:
                    logger.error(f"Failed to delete contract: {contract_id}")
