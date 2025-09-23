#!/usr/bin/env python3
"""
EVE Observer Contract Processor
Handles fetching and processing of EVE contract data.
"""

import os
import json
import requests
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from config import *
from api_client import fetch_public_esi, fetch_esi, wp_request, send_email, fetch_type_icon, sanitize_string, WordPressAuthError, WordPressRequestError
from cache_manager import load_blueprint_cache, save_blueprint_cache, load_blueprint_type_cache, save_blueprint_type_cache

def fetch_public_contracts(region_id: int, page: int = 1, max_retries: int = 3) -> Optional[List[Dict[str, Any]]]:
    """Fetch public contracts for a specific region with retry logic and rate limiting.
    
    This function retrieves public contracts from the EVE ESI API for a given region,
    implementing exponential backoff retry logic and monitoring ESI rate limits.
    
    Args:
        region_id: The EVE region ID to fetch contracts from
        page: Page number for pagination (default: 1)
        max_retries: Maximum number of retry attempts on failure (default: 3)
        
    Returns:
        List of contract dictionaries if successful, None if all retries failed
        
    Note:
        ESI returns a maximum of 1000 contracts per page. Use pagination for complete results.
    """
    endpoint = f"/contracts/public/{region_id}/?page={page}"
    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {'Accept': 'application/json'}
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Check rate limiting
            remaining = response.headers.get('X-ESI-Error-Limit-Remain', '100')
            reset_time = response.headers.get('X-ESI-Error-Limit-Reset', '60')
            if int(remaining) < 20:
                logger.warning(f"ESI rate limit low: {remaining} requests remaining, resets in {reset_time}s")
            
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"ESI request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s")
                time.sleep(wait_time)
            else:
                logger.error(f"ESI request failed after {max_retries} attempts: {e}")
                return None

def fetch_public_contract_items(contract_id: int, max_retries: int = 3) -> Optional[List[Dict[str, Any]]]:
    """Fetch items contained in a public contract with retry logic.
    
    Retrieves the list of items and their quantities for a specific public contract.
    Only works for contracts that are publicly visible (not private courier contracts).
    
    Args:
        contract_id: The EVE contract ID to fetch items for
        max_retries: Maximum number of retry attempts on failure (default: 3)
        
    Returns:
        List of contract item dictionaries if successful, None if failed
        
    Note:
        Item quantities are negative for blueprint originals (BPOs) and positive for copies (BPCs).
    """
    endpoint = f"/contracts/public/items/{contract_id}/"
    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {'Accept': 'application/json'}
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Check rate limiting
            remaining = response.headers.get('X-ESI-Error-Limit-Remain', '100')
            reset_time = response.headers.get('X-ESI-Error-Limit-Reset', '60')
            if int(remaining) < 20:
                logger.warning(f"ESI rate limit low: {remaining} requests remaining, resets in {reset_time}s")
            
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"ESI request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s")
                time.sleep(wait_time)
            else:
                logger.error(f"ESI request failed after {max_retries} attempts: {e}")
                return None

def check_contract_competition(contract_data: Dict[str, Any], contract_items: List[Dict[str, Any]]) -> Tuple[bool, Optional[float]]:
    """Check if a sell contract has been outbid by cheaper competing contracts in the same region.
    
    Analyzes market competition for single-item sell contracts by comparing prices
    against other outstanding contracts for the same item type in the same region.
    
    Args:
        contract_data: Contract information dictionary from ESI
        contract_items: List of items in the contract
        
    Returns:
        Tuple of (is_outbid: bool, competing_price: float or None)
        - is_outbid: True if a cheaper competing contract exists
        - competing_price: The price per item of the cheapest competing contract, or None
        
    Note:
        Only checks single-item sell contracts (item_exchange type) with positive quantities.
        Skips contracts from the same issuer to avoid self-comparison.
    """
    if not contract_items or len(contract_items) != 1:
        return False, None  # Only check single item contracts
    
    contract_type = contract_data.get('type')
    if contract_type != 'item_exchange':
        return False, None  # Only check sell orders
    
    item = contract_items[0]
    type_id = item.get('type_id')
    quantity = item.get('quantity', 1)
    contract_price = contract_data.get('price', 0)
    contract_id = contract_data.get('contract_id')
    contract_issuer_id = contract_data.get('issuer_id')
    
    if not type_id or quantity <= 0 or contract_price <= 0:
        return False, None
    
    price_per_item = contract_price / quantity
    
    # Get contract region
    region_id = get_region_from_location(contract_data.get('start_location_id'))
    if not region_id:
        logger.warning(f"Could not determine region for contract {contract_id}")
        return False, None
    
    logger.info(f"Checking competition for contract {contract_id} (type_id: {type_id}, price_per_item: {price_per_item:.2f}) in region {region_id}")
    
    # Fetch all public contracts in the region
    page = 1
    competing_contracts = []
    
    while True:
        logger.debug(f"Fetching contracts page {page} for region {region_id}")
        contracts_page = fetch_public_contracts(region_id, page)
        if contracts_page is None:
            logger.error(f"Failed to fetch contracts for region {region_id}, page {page}")
            break
        elif not contracts_page:
            logger.debug(f"No contracts returned for region {region_id}, page {page}")
            break
        
        logger.debug(f"Fetched {len(contracts_page)} contracts from region {region_id}, page {page}")
        
        # Filter for outstanding item_exchange contracts
        for contract in contracts_page:
            if (contract.get('type') == 'item_exchange' and 
                contract.get('contract_id') != contract_id and
                contract.get('issuer_id') != contract_issuer_id):
                competing_contracts.append(contract)
        
        # Check if there are more pages
        if len(contracts_page) < 1000:  # ESI returns max 1000 per page
            break
        page += 1
        if page > 10:  # Safety limit to prevent infinite loops
            logger.warning(f"Reached page limit (10) for region {region_id}, stopping")
            break
    
    logger.info(f"Found {len(competing_contracts)} potential competing contracts in region {region_id}")
    
    # Check each competing contract
    for comp_contract in competing_contracts:
        comp_contract_id = comp_contract.get('contract_id')
        comp_price = comp_contract.get('price', 0)
        
        # Fetch contract items
        comp_items = fetch_public_contract_items(comp_contract_id)
        if not comp_items or len(comp_items) != 1:
            continue  # Only check single-item contracts
        
        comp_item = comp_items[0]
        comp_type_id = comp_item.get('type_id')
        comp_quantity = comp_item.get('quantity', 1)
        
        if comp_type_id == type_id and comp_quantity > 0 and comp_price > 0:
            comp_price_per_item = comp_price / comp_quantity
            if comp_price_per_item < price_per_item:
                logger.info(f"Contract {contract_id} outbid by contract {comp_contract_id} with price_per_item: {comp_price_per_item:.2f}")
                return True, comp_price_per_item
    
    logger.info(f"No competing contracts found for contract {contract_id}")
    return False, None

def get_region_from_location(location_id: Optional[int]) -> Optional[int]:
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
    cache_file = 'cache/region_cache.json'
    try:
        with open(cache_file, 'r') as f:
            region_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        region_cache = {}
    
    location_id_str = str(location_id)
    if location_id_str in region_cache:
        return region_cache[location_id_str]
    
    region_id = None
    if location_id >= 1000000000000:  # Structure
        # For structures, we need to fetch structure info to get solar_system_id, then region
        try:
            response = requests.get(f"{ESI_BASE_URL}/universe/structures/{location_id}", headers={'Accept': 'application/json'}, timeout=30)
            response.raise_for_status()
            struct_data = response.json()
        except requests.exceptions.RequestException:
            struct_data = None
        
        if struct_data:
            solar_system_id = struct_data.get('solar_system_id')
            if solar_system_id:
                try:
                    response = requests.get(f"{ESI_BASE_URL}/universe/systems/{solar_system_id}", headers={'Accept': 'application/json'}, timeout=30)
                    response.raise_for_status()
                    system_data = response.json()
                except requests.exceptions.RequestException:
                    system_data = None
                
                if system_data:
                    constellation_id = system_data.get('constellation_id')
                    if constellation_id:
                        try:
                            response = requests.get(f"{ESI_BASE_URL}/universe/constellations/{constellation_id}", headers={'Accept': 'application/json'}, timeout=30)
                            response.raise_for_status()
                            constellation_data = response.json()
                        except requests.exceptions.RequestException:
                            constellation_data = None
                        
                        if constellation_data:
                            region_id = constellation_data.get('region_id')
    else:  # Station
        try:
            response = requests.get(f"{ESI_BASE_URL}/universe/stations/{location_id}", headers={'Accept': 'application/json'}, timeout=30)
            response.raise_for_status()
            station_data = response.json()
        except requests.exceptions.RequestException:
            station_data = None
        
        if station_data:
            system_id = station_data.get('system_id')
            if system_id:
                try:
                    response = requests.get(f"{ESI_BASE_URL}/universe/systems/{system_id}", headers={'Accept': 'application/json'}, timeout=30)
                    response.raise_for_status()
                    system_data = response.json()
                except requests.exceptions.RequestException:
                    system_data = None
                
                if system_data:
                    constellation_id = system_data.get('constellation_id')
                    if constellation_id:
                        try:
                            response = requests.get(f"{ESI_BASE_URL}/universe/constellations/{constellation_id}", headers={'Accept': 'application/json'}, timeout=30)
                            response.raise_for_status()
                            constellation_data = response.json()
                        except requests.exceptions.RequestException:
                            constellation_data = None
                        
                        if constellation_data:
                            region_id = constellation_data.get('region_id')
    
    # Cache the result
    if region_id:
        region_cache[location_id_str] = region_id
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump(region_cache, f, indent=2)
    
    return region_id

def generate_contract_title(contract_data: Dict[str, Any], for_corp: bool = False, entity_id: Optional[int] = None, contract_items: Optional[List[Dict[str, Any]]] = None, blueprint_cache: Optional[Dict[str, Any]] = None) -> str:
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
    
    contract_id = contract_data.get('contract_id')
    contract_type = contract_data.get('type', 'unknown')
    status = contract_data.get('status', 'unknown').title()
    
    # If no items, use default format
    if not contract_items:
        type_names = {
            'item_exchange': 'Item Exchange',
            'auction': 'Auction',
            'courier': 'Courier',
            'loan': 'Loan'
        }
        type_name = type_names.get(contract_type, contract_type.title())
        title = f"Contract {contract_id} - {type_name} ({status})"
    else:
        # If we have items, create a more descriptive title
        if len(contract_items) == 1:
            # Single item contract
            item = contract_items[0]
            type_id = item.get('type_id')
            quantity = item.get('quantity', 1)
            
            if type_id:
                # Get item name
                if str(type_id) in blueprint_cache:
                    item_name = blueprint_cache[str(type_id)]
                else:
                    type_data = fetch_public_esi(f"/universe/types/{type_id}")
                    if type_data:
                        item_name = type_data.get('name', f"Item {type_id}")
                        # Only cache if it's actually a blueprint
                        if 'Blueprint' in item_name:
                            cleaned_name = item_name.replace(" Blueprint", "").strip()
                            blueprint_cache[str(type_id)] = cleaned_name
                            save_blueprint_cache(blueprint_cache)
                    else:
                        item_name = f"Item {type_id}"
                
                # Check if it's a blueprint (quantity -1 indicates BPO, or check if it's in blueprint cache)
                is_blueprint = str(type_id) in blueprint_type_cache and blueprint_type_cache[str(type_id)]
                if not is_blueprint:
                    # Double-check with ESI
                    type_data = fetch_public_esi(f"/universe/types/{type_id}")
                    is_blueprint = type_data and 'Blueprint' in type_data.get('name', '')
                
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
                quantity = item.get('quantity', 1)
                total_quantity += abs(quantity)  # Use abs in case of BPOs
                
                # Check if it's a blueprint
                type_id = item.get('type_id')
                if type_id:
                    # First check if it's in blueprint cache
                    if str(type_id) in blueprint_type_cache and blueprint_type_cache[str(type_id)]:
                        blueprint_count += 1
                    else:
                        # Check with ESI
                        type_data = fetch_public_esi(f"/universe/types/{type_id}")
                        if type_data and 'Blueprint' in type_data.get('name', ''):
                            blueprint_count += 1
            
            if blueprint_count == len(contract_items):
                # All items are blueprints
                title = f"{blueprint_count} Blueprints - Contract {contract_id}"
            elif blueprint_count > 0:
                # Mix of blueprints and other items
                title = f"{blueprint_count} Blueprints + {len(contract_items) - blueprint_count} Items - Contract {contract_id}"
            else:
                # No blueprints, just regular items
                title = f"{len(contract_items)} Items (x{total_quantity}) - Contract {contract_id}"

    if for_corp:
        title = f"[Corp] {title}"
    
    return title

def update_contract_in_wp(contract_id: int, contract_data: Dict[str, Any], for_corp: bool = False, entity_id: Optional[int] = None, access_token: Optional[str] = None, blueprint_cache: Optional[Dict[str, Any]] = None) -> None:
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
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    # Fetch contract items if we have access token
    contract_items = None
    if access_token:
        if for_corp and entity_id:
            contract_items = fetch_corporation_contract_items(entity_id, contract_id, access_token)
        elif not for_corp and entity_id:
            contract_items = fetch_character_contract_items(entity_id, contract_id, access_token)

    # Get region ID from start location
    region_id = None
    start_location_id = contract_data.get('start_location_id')
    if start_location_id:
        region_id = get_region_from_location(start_location_id)

    # Check if contract contains blueprints - only track contracts with blueprints
    has_blueprint = False
    if contract_items:
        for item in contract_items:
            type_id = item.get('type_id')
            if type_id and str(type_id) in blueprint_type_cache and blueprint_type_cache[str(type_id)]:
                has_blueprint = True
                break
    
    if not has_blueprint:
        logger.info(f"Contract {contract_id} contains no blueprints, skipping")
        return

    title = generate_contract_title(contract_data, for_corp=for_corp, entity_id=entity_id, contract_items=contract_items, blueprint_cache=blueprint_cache)

    post_data = {
        'title': title,
        'slug': slug,
        'status': 'publish',
        'meta': {
            '_eve_contract_id': str(contract_id),
            '_eve_contract_type': contract_data.get('type'),
            '_eve_contract_status': contract_data.get('status'),
            '_eve_contract_issuer_id': str(contract_data.get('issuer_id')) if contract_data.get('issuer_id') is not None else None,
            '_eve_contract_issuer_corp_id': str(contract_data.get('issuer_corporation_id')) if contract_data.get('issuer_corporation_id') is not None else None,
            '_eve_contract_assignee_id': str(contract_data.get('assignee_id')) if contract_data.get('assignee_id') else None,
            '_eve_contract_acceptor_id': str(contract_data.get('acceptor_id')) if contract_data.get('acceptor_id') else None,
            '_eve_contract_start_location_id': str(contract_data.get('start_location_id')) if contract_data.get('start_location_id') else None,
            '_eve_contract_end_location_id': str(contract_data.get('end_location_id')) if contract_data.get('end_location_id') else None,
            '_eve_contract_region_id': str(region_id) if region_id else None,
            '_eve_contract_date_issued': contract_data.get('date_issued'),
            '_eve_contract_date_expired': contract_data.get('date_expired'),
            '_eve_contract_date_accepted': contract_data.get('date_accepted'),
            '_eve_contract_date_completed': contract_data.get('date_completed'),
            '_eve_contract_price': str(contract_data.get('price')) if contract_data.get('price') is not None else None,
            '_eve_contract_reward': str(contract_data.get('reward')) if contract_data.get('reward') is not None else None,
            '_eve_contract_collateral': str(contract_data.get('collateral')) if contract_data.get('collateral') is not None else None,
            '_eve_contract_buyout': str(contract_data.get('buyout')) if contract_data.get('buyout') is not None else None,
            '_eve_contract_volume': str(contract_data.get('volume')) if contract_data.get('volume') is not None else None,
            '_eve_contract_days_to_complete': str(contract_data.get('days_to_complete')) if contract_data.get('days_to_complete') is not None else None,
            '_eve_contract_title': contract_data.get('title'),
            '_eve_contract_for_corp': str(for_corp).lower(),
            '_eve_contract_entity_id': str(entity_id),
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Remove null values from meta to avoid WordPress validation errors
    post_data['meta'] = {k: v for k, v in post_data['meta'].items() if v is not None}

    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None
    existing_meta = existing_post.get('meta', {}) if existing_post else {}

    # Add items data if available
    if contract_items:
        post_data['meta']['_eve_contract_items'] = json.dumps(contract_items)
        
        # Store item types for easier querying
        item_types = [str(item.get('type_id')) for item in contract_items if item.get('type_id')]
        post_data['meta']['_eve_contract_item_types'] = ','.join(item_types)
        
        # Check for market competition on outstanding sell contracts
        if contract_data.get('status') == 'outstanding' and contract_data.get('type') == 'item_exchange':
            is_outbid, competing_price = check_contract_competition(contract_data, contract_items)
            if is_outbid:
                post_data['meta']['_eve_contract_outbid'] = '1'
                post_data['meta']['_eve_contract_competing_price'] = str(competing_price)
                logger.warning(f"Contract {contract_id} is outbid by contract price: {competing_price}")
                
                # Send alert if this is newly outbid
                was_outbid = existing_meta.get('_eve_contract_outbid') == '1'
                if not was_outbid:
                    logger.warning(f"Contract {contract_id} is outbid by contract price: {competing_price}")
            else:
                post_data['meta']['_eve_contract_outbid'] = '0'
                if '_eve_contract_competing_price' in post_data['meta']:
                    del post_data['meta']['_eve_contract_competing_price']
        else:
            # Not a sell contract or not outstanding - ensure outbid is false
            post_data['meta']['_eve_contract_outbid'] = '0'
            if '_eve_contract_competing_price' in post_data['meta']:
                del post_data['meta']['_eve_contract_competing_price']
    else:
        # No contract items - ensure outbid is set to false
        post_data['meta']['_eve_contract_outbid'] = '0'
        if '_eve_contract_competing_price' in post_data['meta']:
            del post_data['meta']['_eve_contract_competing_price']

    if existing_post:
        # Check if title changed before updating
        existing_title = existing_post.get('title', {}).get('rendered', '')
        
        # Compare key fields to see if update is needed
        needs_update = (
            existing_title != title or
            str(existing_meta.get('_eve_contract_status', '')) != str(contract_data.get('status', '')) or
            str(existing_meta.get('_eve_contract_items', '')) != str(json.dumps(contract_items) if contract_items else '') or
            str(existing_meta.get('_eve_contract_outbid', '0')) != str(post_data['meta'].get('_eve_contract_outbid', '0'))
        )
        
        if not needs_update:
            logger.info(f"Contract {contract_id} unchanged, skipping update")
            return
        
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new (without region_id to avoid ACF protection issues)
        # Add thumbnail from first contract item
        if contract_items and len(contract_items) > 0:
            first_item_type_id = contract_items[0].get('type_id')
            if first_item_type_id:
                image_url = fetch_type_icon(first_item_type_id, size=512)
                post_data['meta']['_thumbnail_external_url'] = image_url
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        logger.info(f"Updated contract: {contract_id} - {title}")
    else:
        logger.error(f"Failed to update contract {contract_id}: {response.status_code} - {response.text}")

def fetch_character_contract_items(char_id: int, contract_id: int, access_token: str) -> Optional[List[Dict[str, Any]]]:
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
    return fetch_esi(endpoint, char_id, access_token)

def fetch_corporation_contract_items(corp_id: int, contract_id: int, access_token: str) -> Optional[List[Dict[str, Any]]]:
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
    return fetch_esi(endpoint, None, access_token)  # Corp endpoint doesn't need char_id