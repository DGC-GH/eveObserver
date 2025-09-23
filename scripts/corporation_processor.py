#!/usr/bin/env python3
"""
EVE Observer Corporation Processor
Handles processing of corporation-specific data.
"""

import requests
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from config import *
from api_client import fetch_esi, fetch_public_esi, get_wp_auth
from blueprint_processor import extract_blueprints_from_assets, extract_blueprints_from_industry_jobs, extract_blueprints_from_contracts, process_blueprints_parallel, update_blueprint_in_wp, update_blueprint_from_asset_in_wp

async def fetch_corporation_data(corp_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch corporation information from ESI.

    Retrieves basic corporation data including name, ticker, member count,
    alliance affiliation, and other corporation attributes.

    Args:
        corp_id: EVE corporation ID to fetch data for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Corporation data dictionary if successful.
    """
    endpoint = f"/corporations/{corp_id}/"
    return await fetch_esi(endpoint, None, access_token)  # No char_id needed for corp data

async def fetch_corporation_blueprints(corp_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch corporation blueprint collection from ESI.

    Retrieves all blueprints owned by the corporation, including both BPOs and BPCs,
    with their ME/TE levels, location, and other blueprint attributes.

    Args:
        corp_id: EVE corporation ID to fetch blueprints for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Blueprint data array if successful.
    """
    endpoint = f"/corporations/{corp_id}/blueprints/"
    return await fetch_esi(endpoint, corp_id, access_token)

async def fetch_corporation_contracts(corp_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch corporation contracts from ESI.

    Retrieves all contracts issued by the corporation, including item exchanges,
    auctions, courier contracts, and other contract types.

    Args:
        corp_id: EVE corporation ID to fetch contracts for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Contracts data array if successful.
    """
    endpoint = f"/corporations/{corp_id}/contracts/"
    return await fetch_esi(endpoint, None, access_token)  # Corp contracts don't need char_id

def fetch_corporation_contract_items(corp_id: int, contract_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch items in a specific corporation contract from ESI.

    Retrieves the detailed list of items included in a corporation contract,
    including quantities and types for contract analysis.

    Args:
        corp_id: EVE corporation ID that issued the contract.
        contract_id: Specific contract ID to fetch items for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Contract items data array if successful.
    """
    endpoint = f"/corporations/{corp_id}/contracts/{contract_id}/items/"
    return fetch_esi(endpoint, None, access_token)  # Corp endpoint doesn't need char_id

async def fetch_corporation_industry_jobs(corp_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch corporation industry jobs from ESI.

    Retrieves all active industry jobs for the corporation, including manufacturing,
    research, and other industry activities.

    Args:
        corp_id: EVE corporation ID to fetch industry jobs for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Industry jobs data array if successful.
    """
    endpoint = f"/corporations/{corp_id}/industry/jobs/"
    return await fetch_esi(endpoint, corp_id, access_token)

async def fetch_corporation_assets(corp_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch corporation assets from ESI.

    Retrieves the complete list of items owned by the corporation across all locations,
    including items in stations, structures, and ships.

    Args:
        corp_id: EVE corporation ID to fetch assets for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Assets data array if successful.
    """
    endpoint = f"/corporations/{corp_id}/assets/"
    return await fetch_esi(endpoint, None, access_token)  # Corp endpoint doesn't need char_id

async def fetch_corporation_logo(corp_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetch corporation logo image URLs from ESI.

    Retrieves corporation logo URLs in multiple sizes (64x64, 128x128, 256x256, 512x512)
    for use as featured images in WordPress corporation posts.

    Args:
        corp_id: EVE corporation ID to fetch logo for.

    Returns:
        Optional[Dict[str, Any]]: Logo URLs dictionary with size keys if successful,
                                 None if fetch failed.

    Note:
        This is a public endpoint that doesn't require authentication.
    """
    endpoint = f"/corporations/{corp_id}/logo/"
    return await fetch_public_esi(endpoint)

async def select_corporation_token(corp_id: int, members: List[Tuple[int, str, str]]) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[Dict[str, Any]]]:
    """
    Select the best token for accessing corporation data.

    For No Mercy Incorporated, prioritizes Dr FiLiN's CEO token.
    For other corporations, tries each member token until one works.

    Args:
        corp_id: The corporation ID
        members: List of (char_id, access_token, char_name) tuples

    Returns:
        Tuple of (access_token, char_name, char_id, corp_data) or (None, None, None, None) if no token works
    """
    # For No Mercy Incorporated, prioritize Dr FiLiN's token (CEO)
    if corp_id == 98092220:  # No Mercy Incorporated
        # Find Dr FiLiN's token
        dr_filin_token = None
        dr_filin_char_id = None
        dr_filin_name = None
        for char_id, access_token, char_name in members:
            if char_name == 'Dr FiLiN':
                dr_filin_token = access_token
                dr_filin_char_id = char_id
                dr_filin_name = char_name
                break
        
        if dr_filin_token:
            logger.info(f"Using Dr FiLiN's CEO token for No Mercy Incorporated")
            corp_data = await fetch_corporation_data(corp_id, dr_filin_token)
            if corp_data:
                return dr_filin_token, dr_filin_name, dr_filin_char_id, corp_data
            else:
                logger.warning(f"Dr FiLiN's token failed for corporation {corp_id}, falling back to other members")
    
    # Try each member token until one works
    for char_id, access_token, char_name in members:
        # Skip Dr FiLiN if we already tried them for No Mercy
        if corp_id == 98092220 and char_name == 'Dr FiLiN':
            continue
            
        logger.info(f"Trying to fetch corporation data for corp {corp_id} using {char_name}'s token...")
        corp_data = await fetch_corporation_data(corp_id, access_token)
        if corp_data:
            logger.info(f"Successfully fetched corporation data using {char_name}'s token")
            return access_token, char_name, char_id, corp_data
        else:
            logger.warning(f"Failed to fetch corporation data using {char_name}'s token (likely no access)")
    
    return None, None, None, None

async def process_corporation_data(corp_id: int, members: List[Tuple[int, str, str]], wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any], args: argparse.Namespace) -> None:
    """
    Process data for a single corporation and its members.

    Fetches and processes corporation information, blueprints from multiple sources,
    and corporation contracts based on command line arguments.

    Args:
        corp_id: Corporation ID to process.
        members: List of corporation member tuples (char_id, access_token, char_name).
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
        args: Parsed command line arguments.

    Note:
        Only processes corporations in the ALLOWED_CORPORATIONS list.
        Corporation contracts are processed via character contract processing.
    """
    # Select the best token for corporation access
    access_token, char_name, char_id, corp_data = await select_corporation_token(corp_id, members)
    
    if not corp_data:
        return

    corp_name = corp_data.get('name', '')
    if corp_name.lower() not in ALLOWED_CORPORATIONS:
        logger.info(f"Skipping corporation: {corp_name} (only processing {ALLOWED_CORPORATIONS})")
        return

    if args.all or args.corporations:
        update_corporation_in_wp(corp_id, corp_data)

    # Process corporation blueprints from various sources
    if args.all or args.blueprints:
        await process_corporation_blueprints(corp_id, access_token, char_id, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures)

    # Corporation contracts are processed via character contracts (issued by corp members)
    if args.all or args.contracts:
        await process_corporation_contracts(corp_id, access_token, corp_data, blueprint_cache)

async def process_corporation_blueprints_from_endpoint(corp_id: int, access_token: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process corporation blueprints from the direct blueprints endpoint.

    Fetches blueprints directly from the corporation's blueprint endpoint,
    filters to BPOs only, and processes them in parallel.

    Args:
        corp_id: Corporation ID to fetch blueprints for.
        access_token: Valid access token for corporation data.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    logger.info(f"Fetching corporation blueprints for {corp_id}...")
    
    corp_blueprints = await fetch_corporation_blueprints(corp_id, access_token)
    if corp_blueprints:
        # Filter to only BPOs (quantity == -1)
        bpo_blueprints = [bp for bp in corp_blueprints if bp.get('quantity', 1) == -1]
        logger.info(f"Corporation blueprints: {len(corp_blueprints)} total, {len(bpo_blueprints)} BPOs")
        if bpo_blueprints:
            # Process blueprints in parallel
            await process_blueprints_parallel(
                bpo_blueprints,
                update_blueprint_in_wp,
                wp_post_id_cache,
                corp_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

async def process_corporation_blueprints_from_assets(corp_id: int, access_token: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process corporation blueprints from corporation assets.

    Extracts blueprints from corporation asset lists and processes them.
    Can be disabled via SKIP_CORPORATION_ASSETS configuration.

    Args:
        corp_id: Corporation ID to fetch assets for.
        access_token: Valid access token for corporation data.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    logger.info(f"Fetching corporation assets for {corp_id}...")
    if SKIP_CORPORATION_ASSETS:
        logger.info("Skipping corporation assets processing (SKIP_CORPORATION_ASSETS=true)")
        return
        
    corp_assets = await fetch_corporation_assets(corp_id, access_token)
    if corp_assets:
        logger.info(f"Fetched {len(corp_assets)} corporation assets")
        asset_blueprints = extract_blueprints_from_assets(corp_assets, 'corp', corp_id, access_token)
        if asset_blueprints:
            logger.info(f"Corporation asset blueprints: {len(asset_blueprints)} items")
            # Process blueprints in parallel
            await process_blueprints_parallel(
                asset_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                corp_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )
        else:
            logger.info("No blueprints found in corporation assets")
    else:
        logger.info("No corporation assets found or access denied")

async def process_corporation_blueprints_from_industry_jobs(corp_id: int, access_token: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process corporation blueprints from corporation industry jobs.

    Extracts blueprints from active corporation industry jobs and processes them.

    Args:
        corp_id: Corporation ID to fetch industry jobs for.
        access_token: Valid access token for corporation data.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    corp_industry_jobs = await fetch_corporation_industry_jobs(corp_id, access_token)
    if corp_industry_jobs:
        job_blueprints = extract_blueprints_from_industry_jobs(corp_industry_jobs, 'corp', corp_id)
        if job_blueprints:
            logger.info(f"Corporation industry job blueprints: {len(job_blueprints)} items")
            # Process blueprints in parallel
            await process_blueprints_parallel(
                job_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                corp_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

async def process_corporation_blueprints_from_contracts(corp_id: int, access_token: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process corporation blueprints from corporation contracts.

    Extracts blueprints from corporation contract items and processes them.

    Args:
        corp_id: Corporation ID to fetch contracts for.
        access_token: Valid access token for corporation data.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    corp_contracts = await fetch_corporation_contracts(corp_id, access_token)
    if corp_contracts:
        contract_blueprints = extract_blueprints_from_contracts(corp_contracts, 'corp', corp_id)
        if contract_blueprints:
            logger.info(f"Corporation contract blueprints: {len(contract_blueprints)} items")
            # Process blueprints in parallel
            await process_blueprints_parallel(
                contract_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                corp_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

async def process_corporation_blueprints(corp_id: int, access_token: str, char_id: int, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process all blueprint sources for a corporation.

    Orchestrates blueprint processing from all available sources:
    direct endpoint, assets, industry jobs, and contracts.

    Args:
        corp_id: Corporation ID to process blueprints for.
        access_token: Valid access token for corporation data.
        char_id: Character ID for context (may be None).
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    # Process blueprints from different sources
    await process_corporation_blueprints_from_endpoint(
        corp_id, access_token, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures
    )
    
    await process_corporation_blueprints_from_assets(
        corp_id, access_token, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures
    )
    
    await process_corporation_blueprints_from_industry_jobs(
        corp_id, access_token, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures
    )
    
    await process_corporation_blueprints_from_contracts(
        corp_id, access_token, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures
    )

async def process_corporation_contracts(corp_id: int, access_token: str, corp_data: Dict[str, Any], blueprint_cache: Dict[str, Any]) -> None:
    """
    Process contracts for a corporation.

    Fetches corporation contracts and processes those issued by this corporation,
    skipping finished/deleted contracts for performance.

    Args:
        corp_id: Corporation ID to process contracts for.
        access_token: Valid access token for corporation data.
        corp_data: Corporation data dictionary.
        blueprint_cache: Blueprint name cache for contract title generation.
    """
    from contract_processor import update_contract_in_wp

    corp_contracts = await fetch_corporation_contracts(corp_id, access_token)
    if corp_contracts:
        logger.info(f"Corporation contracts for {corp_data.get('name', corp_id)}: {len(corp_contracts)} items")
        for contract in corp_contracts:
            contract_status = contract.get('status', '')
            if contract_status in ['finished', 'deleted']:
                # Skip finished/deleted contracts to improve performance
                continue
            elif contract_status == 'expired':
                logger.info(f"EXPIRED CORPORATION CONTRACT TO DELETE MANUALLY: {contract['contract_id']}")
            
            # Only process contracts issued by this corporation
            if contract.get('issuer_corporation_id') != corp_id:
                continue
                
            update_contract_in_wp(contract['contract_id'], contract, for_corp=True, entity_id=corp_id, access_token=access_token, blueprint_cache=blueprint_cache)

def update_corporation_in_wp(corp_id: int, corp_data: Dict[str, Any]) -> None:
    """Update or create corporation post in WordPress with corporation details.
    
    Creates or updates WordPress posts for EVE corporations with comprehensive
    metadata including member count, CEO, alliance affiliation, and other details.
    
    Args:
        corp_id: EVE corporation ID
        corp_data: Corporation information dictionary from ESI API
        
    Returns:
        None
        
    Note:
        Stores corporation details as post metadata in WordPress.
        Removes null values from metadata to avoid WordPress validation issues.
        Updates existing posts or creates new ones based on slug lookup.
    """
    slug = f"corporation-{corp_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    post_data = {
        'title': corp_data.get('name', f'Corporation {corp_id}'),
        'slug': slug,
        'status': 'publish',
        'meta': {
            '_eve_corp_id': corp_id,
            '_eve_corp_name': corp_data.get('name'),
            '_eve_corp_ticker': corp_data.get('ticker'),
            '_eve_corp_member_count': corp_data.get('member_count'),
            '_eve_corp_ceo_id': corp_data.get('ceo_id'),
            '_eve_corp_alliance_id': corp_data.get('alliance_id'),
            '_eve_corp_date_founded': corp_data.get('date_founded'),
            '_eve_corp_tax_rate': corp_data.get('tax_rate'),
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Remove null values
    post_data['meta'] = {k: v for k, v in post_data['meta'].items() if v is not None}

    if existing_post:
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        logger.info(f"Updated corporation: {corp_data.get('name', corp_id)}")
    else:
        logger.error(f"Failed to update corporation {corp_id}: {response.status_code} - {response.text}")