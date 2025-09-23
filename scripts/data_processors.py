#!/usr/bin/env python3
"""
EVE Observer Data Processors
Handles processing and updating of EVE data in WordPress.
"""

import os
import json
import requests
import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Callable
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import time
import asyncio

from config import *
from api_client import fetch_public_esi, fetch_esi, wp_request, send_email, refresh_token, fetch_type_icon, sanitize_string, WordPressAuthError, WordPressRequestError, ESIAuthError, ESIRequestError, log_audit_event, benchmark, format_error_message
from cache_manager import (
    load_blueprint_cache, save_blueprint_cache, load_blueprint_type_cache, save_blueprint_type_cache,
    load_location_cache, save_location_cache, load_structure_cache, save_structure_cache,
    load_failed_structures, save_failed_structures, load_wp_post_id_cache, save_wp_post_id_cache,
    get_cached_wp_post_id, set_cached_wp_post_id, get_cache_stats, log_cache_performance,
    get_cached_value_with_stats, flush_pending_saves
)

logger = logging.getLogger(__name__)

def get_wp_auth() -> requests.auth.HTTPBasicAuth:
    """Get WordPress authentication."""
    return requests.auth.HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)

async def process_blueprints_parallel(blueprints: List[Dict[str, Any]], update_func: Callable[..., Any], wp_post_id_cache: Dict[str, Any], *args, **kwargs) -> List[Any]:
    """Process blueprints in parallel using asyncio for better concurrency."""
    start_time = time.time()
    total_blueprints = len(blueprints)

    logger.info(f"Starting async processing of {total_blueprints} blueprints")

    tasks = [update_func(bp, wp_post_id_cache, *args, **kwargs) for bp in blueprints]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed_count = 0
    for result in results:
        if isinstance(result, Exception):
            logger.error(f'Blueprint processing generated an exception: {result}')
        else:
            processed_count += 1
            logger.info(f"Processed blueprint {processed_count}/{total_blueprints}")

    elapsed = time.time() - start_time
    logger.info(f"Blueprint processing completed for {total_blueprints} blueprints in {elapsed:.2f}s")

    return results

async def update_or_create_blueprint_post(post_data: Dict[str, Any], existing_post: Optional[Dict[str, Any]], wp_post_id_cache: Dict[str, Any], item_id: int, blueprint_data: Dict[str, Any], type_name: str, location_name: str, me: int, te: int, quantity: int, char_id: int) -> None:
    """
    Update or create the blueprint post in WordPress.
    """
    # Add featured image from type icon (only for new blueprints)
    if not existing_post:
        type_id = blueprint_data.get('type_id')
        if type_id:
            image_url = await fetch_type_icon(type_id, size=512)
            post_data['meta']['_thumbnail_external_url'] = image_url

    if existing_post:
        # Check if data has changed before updating
        existing_meta = existing_post.get('meta', {})
        existing_title = existing_post.get('title', {}).get('rendered', '')

        # Compare key fields
        needs_update = (
            existing_title != post_data['title'] or
            str(existing_meta.get('_eve_bp_location_name', '')) != str(location_name) or
            str(existing_meta.get('_eve_bp_me', 0)) != str(me) or
            str(existing_meta.get('_eve_bp_te', 0)) != str(te) or
            str(existing_meta.get('_eve_bp_quantity', -1)) != str(quantity)
        )

        if not needs_update:
            logger.info(f"Blueprint {item_id} unchanged, skipping update")
            return

        # Update existing
        post_id = existing_post['id']
        try:
            result = await wp_request('PUT', f"/wp-json/wp/v2/eve_blueprint/{post_id}", post_data)
            if result:
                logger.info(f"Updated blueprint: {item_id}")
                log_audit_event('BLUEPRINT_UPDATE', str(char_id), {'item_id': item_id, 'post_id': post_id})
            else:
                logger.error(f"Failed to update blueprint {item_id}: No result")
        except (WordPressAuthError, WordPressRequestError) as e:
            logger.error(f"Failed to update blueprint {item_id}: {e}")
    else:
        # Create new
        try:
            new_post = await wp_request('POST', "/wp-json/wp/v2/eve_blueprint", post_data)
            if new_post:
                set_cached_wp_post_id(wp_post_id_cache, 'eve_blueprint', item_id, new_post['id'])
                logger.info(f"Created new blueprint: {item_id}")
                log_audit_event('BLUEPRINT_CREATE', str(char_id), {'item_id': item_id, 'post_id': new_post['id']})
            else:
                logger.error(f"Failed to create blueprint {item_id}: No result")
        except (WordPressAuthError, WordPressRequestError) as e:
            logger.error(f"Failed to create blueprint {item_id}: {e}")

async def update_character_in_wp(char_id: int, char_data: Dict[str, Any]) -> None:
    """
    Update or create a character post in WordPress.

    Fetches character portrait data and updates the post with basic character information,
    including optional fields like corporation, alliance, and security status.

    Args:
        char_id: The EVE character ID.
        char_data: Dictionary containing character data from ESI API.

    Returns:
        None

    Raises:
        No explicit raises; logs errors internally.
    """
    slug = f"character-{char_id}"
    # Check if post exists by slug
    try:
        existing_posts = await wp_request('GET', f"/wp-json/wp/v2/eve_character?slug={slug}")
        existing_post = existing_posts[0] if existing_posts else None
    except (WordPressAuthError, WordPressRequestError) as e:
        logger.error(f"Failed to fetch existing character post for {char_id}: {e}")
        return

    post_data = {
        'title': char_data['name'],
        'slug': f"character-{char_id}",
        'status': 'publish',
        'meta': {
            '_eve_char_id': char_id,
            '_eve_char_name': char_data['name'],
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Add optional fields if they exist
    optional_fields = {
        '_eve_corporation_id': char_data.get('corporation_id'),
        '_eve_alliance_id': char_data.get('alliance_id'),
        '_eve_birthday': char_data.get('birthday'),
        '_eve_gender': char_data.get('gender'),
        '_eve_race_id': char_data.get('race_id'),
        '_eve_bloodline_id': char_data.get('bloodline_id'),
        '_eve_ancestry_id': char_data.get('ancestry_id'),
        '_eve_security_status': char_data.get('security_status')
    }
    for key, value in optional_fields.items():
        if value is not None:
            post_data['meta'][key] = value

    # Add featured image from character portrait
    portrait_data = await fetch_character_portrait(char_id)
    if portrait_data and 'px256x256' in portrait_data:
        new_portrait_url = portrait_data['px256x256']
        # Check if portrait changed before updating
        existing_portrait_url = existing_post.get('meta', {}).get('_thumbnail_external_url') if existing_post else None
        if existing_portrait_url != new_portrait_url:
            post_data['meta']['_thumbnail_external_url'] = new_portrait_url
            logger.info(f"Updated portrait for character: {char_data['name']}")
        else:
            logger.info(f"Portrait unchanged for character: {char_data['name']}")

    if existing_post:
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_character/{post_id}"
        try:
            result = await wp_request('PUT', f"/wp-json/wp/v2/eve_character/{post_id}", post_data)
            if result:
                logger.info(f"Updated character: {char_data['name']}")
                log_audit_event('CHARACTER_UPDATE', str(char_id), {'name': char_data['name'], 'post_id': post_id})
            else:
                logger.error(f"Failed to update character {char_data['name']}: No result")
        except (WordPressAuthError, WordPressRequestError) as e:
            logger.error(f"Failed to update character {char_data['name']}: {e}")
    else:
        # Create new
        try:
            result = await wp_request('POST', "/wp-json/wp/v2/eve_character", post_data)
            if result:
                logger.info(f"Created character: {char_data['name']}")
                log_audit_event('CHARACTER_CREATE', str(char_id), {'name': char_data['name'], 'post_id': result['id']})
            else:
                logger.error(f"Failed to create character {char_data['name']}: No result")
        except (WordPressAuthError, WordPressRequestError) as e:
            logger.error(f"Failed to create character {char_data['name']}: {e}")

async def update_character_skills_in_wp(char_id: int, skills_data: Dict[str, Any]) -> None:
    """Update character post with skills data."""
    slug = f"character-{char_id}"
    # Check if post exists by slug
    try:
        existing_posts = await wp_request('GET', f"/wp-json/wp/v2/eve_character?slug={slug}")
        existing_post = existing_posts[0] if existing_posts else None
    except (WordPressAuthError, WordPressRequestError) as e:
        logger.error(f"Failed to fetch character post for skills update {char_id}: {e}")
        return

    if existing_post:
        post_id = existing_post['id']
        # Update with skills data
        post_data = {
            'meta': {
                '_eve_total_sp': skills_data.get('total_sp', 0),
                '_eve_last_updated': datetime.now(timezone.utc).isoformat()
            }
        }
        try:
            result = await wp_request('PUT', f"/wp-json/wp/v2/eve_character/{post_id}", post_data)
            if result:
                logger.info(f"Updated skills for character {char_id}")
            else:
                logger.error(f"Failed to update skills for character {char_id}: No result")
        except (WordPressAuthError, WordPressRequestError) as e:
            logger.error(f"Failed to update skills for character {char_id}: {e}")

def fetch_character_data(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch basic character data from ESI."""
    try:
        endpoint = f"/characters/{char_id}/"
        return fetch_esi(endpoint, char_id, access_token)
    except (ESIAuthError, ESIRequestError) as e:
        logger.error(format_error_message("fetch_character_data", char_id, e))
        return None

def fetch_character_skills(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch character skills."""
    try:
        endpoint = f"/characters/{char_id}/skills/"
        return fetch_esi(endpoint, char_id, access_token)
    except (ESIAuthError, ESIRequestError) as e:
        logger.error(format_error_message("fetch_character_skills", char_id, e))
        return None

def fetch_character_blueprints(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch character blueprints."""
    try:
        endpoint = f"/characters/{char_id}/blueprints/"
        return fetch_esi(endpoint, char_id, access_token)
    except (ESIAuthError, ESIRequestError) as e:
        logger.error(format_error_message("fetch_character_blueprints", char_id, e))
        return None

def fetch_character_planets(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch character planets."""
    try:
        endpoint = f"/characters/{char_id}/planets/"
        return fetch_esi(endpoint, char_id, access_token)
    except (ESIAuthError, ESIRequestError) as e:
        logger.error(format_error_message("fetch_character_planets", char_id, e))
        return None

def fetch_corporation_data(corp_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch corporation data from ESI."""
    try:
        endpoint = f"/corporations/{corp_id}/"
        return fetch_esi(endpoint, None, access_token)  # No char_id needed for corp data
    except (ESIAuthError, ESIRequestError) as e:
        logger.error(format_error_message("fetch_corporation_data", corp_id, e))
        return None

async def _initialize_blueprint_caches(blueprint_cache: Optional[Dict[str, Any]], location_cache: Optional[Dict[str, Any]], structure_cache: Optional[Dict[str, Any]], failed_structures: Optional[Dict[str, Any]], wp_post_id_cache: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Initialize all caches needed for blueprint processing."""
    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()
    if location_cache is None:
        location_cache = load_location_cache()
    if structure_cache is None:
        structure_cache = load_structure_cache()
    if failed_structures is None:
        failed_structures = load_failed_structures()
    if wp_post_id_cache is None:
        wp_post_id_cache = load_wp_post_id_cache()
    
    return blueprint_cache, location_cache, structure_cache, failed_structures, wp_post_id_cache

async def _validate_and_filter_blueprint(blueprint_data: Dict[str, Any]) -> Optional[int]:
    """Validate blueprint data and filter out BPCs. Returns item_id if valid BPO, None otherwise."""
    item_id = blueprint_data.get('item_id')
    if not item_id:
        logger.error(f"Blueprint data missing item_id: {blueprint_data}")
        return None

    # Skip BPCs - only track BPOs (quantity == -1 indicates a BPO)
    quantity = blueprint_data.get('quantity', -1)
    if quantity != -1:
        logger.info(f"Skipping BPC (quantity={quantity}) for item_id: {item_id}")
        return None
    
    return item_id

async def _find_existing_blueprint_post(item_id: int, wp_post_id_cache: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find existing blueprint post by item_id. Returns post data or None."""
    slug = f"blueprint-{item_id}"

    # Try to get post ID from cache first
    cached_post_id = get_cached_wp_post_id(wp_post_id_cache, 'eve_blueprint', item_id)

    existing_post = None
    if cached_post_id:
        # Use direct post ID lookup
        try:
            existing_post = await wp_request('GET', f"/wp-json/wp/v2/eve_blueprint/{cached_post_id}")
        except (WordPressAuthError, WordPressRequestError) as e:
            logger.error(f"Failed to fetch existing blueprint post {cached_post_id}: {e}")
            cached_post_id = None
            existing_post = None
    else:
        # Fall back to slug lookup
        try:
            existing_posts = await wp_request('GET', f"/wp-json/wp/v2/eve_blueprint?slug={slug}")
            existing_post = existing_posts[0] if existing_posts else None

            # Cache the post ID if found
            if existing_post:
                set_cached_wp_post_id(wp_post_id_cache, 'eve_blueprint', item_id, existing_post['id'])
        except (WordPressAuthError, WordPressRequestError) as e:
            logger.error(f"Failed to fetch blueprint posts by slug {slug}: {e}")
            existing_post = None
    
    return existing_post

async def _prepare_blueprint_data(blueprint_data: Dict[str, Any], char_id: int, access_token: str, blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> Tuple[Dict[str, Any], str, str, str]:
    """Prepare blueprint post data with all required information."""
    # Fetch blueprint details
    type_name, location_name, bp_type = await fetch_blueprint_details(blueprint_data, char_id, access_token, blueprint_cache, location_cache, structure_cache, failed_structures)
    
    item_id = blueprint_data['item_id']
    post_data = construct_blueprint_post_data(blueprint_data, type_name, location_name, bp_type, char_id, item_id)
    
    return post_data, type_name, location_name, bp_type

async def update_blueprint_in_wp(blueprint_data: Dict[str, Any], char_id: int, access_token: str, wp_post_id_cache: Optional[Dict[str, Any]] = None, blueprint_cache: Optional[Dict[str, Any]] = None, location_cache: Optional[Dict[str, Any]] = None, structure_cache: Optional[Dict[str, Any]] = None, failed_structures: Optional[Dict[str, Any]] = None) -> None:
    """
    Update or create a blueprint post in WordPress from direct blueprint endpoint data.

    Processes blueprint information including ME/TE levels, location, and type details.
    Only tracks BPOs (quantity == -1), skipping BPCs. Caches location and type data
    for performance.

    Args:
        blueprint_data: Blueprint data from ESI API.
        wp_post_id_cache: Cache of WordPress post IDs.
        char_id: Character ID for auth.
        access_token: Valid OAuth access token.
        blueprint_cache: Optional cache for blueprint names.
        location_cache: Optional cache for location names.
        structure_cache: Optional cache for structure names.
        failed_structures: Optional cache for failed structure fetches.

    Returns:
        None

    Raises:
        No explicit raises; logs errors internally.
    """
    start_time = time.time()
    
    # Initialize caches
    blueprint_cache, location_cache, structure_cache, failed_structures, wp_post_id_cache = await _initialize_blueprint_caches(
        blueprint_cache, location_cache, structure_cache, failed_structures, wp_post_id_cache
    )
    
    # Validate and filter blueprint
    item_id = await _validate_and_filter_blueprint(blueprint_data)
    if item_id is None:
        return
    
    # Find existing post
    existing_post = await _find_existing_blueprint_post(item_id, wp_post_id_cache)
    
    # Prepare blueprint data
    post_data, type_name, location_name, bp_type = await _prepare_blueprint_data(
        blueprint_data, char_id, access_token, blueprint_cache, location_cache, structure_cache, failed_structures
    )
    
    # Update or create the blueprint post in WordPress
    await update_or_create_blueprint_post(post_data, existing_post, wp_post_id_cache, item_id, blueprint_data, type_name, location_name, 
                                        blueprint_data.get('material_efficiency', 0), blueprint_data.get('time_efficiency', 0), 
                                        blueprint_data.get('quantity', -1), char_id)

    elapsed = time.time() - start_time
    logger.info(f"Blueprint processing completed for item {item_id} in {elapsed:.2f}s")

async def fetch_blueprint_details(blueprint_data: Dict[str, Any], char_id: int, access_token: str, blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Fetch blueprint type name and location name.
    
    Returns:
        Tuple of (type_name, location_name, bp_type)
    """
    item_id = blueprint_data.get('item_id')
    type_id = blueprint_data.get('type_id')
    location_id = blueprint_data.get('location_id')
    quantity = blueprint_data.get('quantity', -1)
    
    # Get blueprint name from cache or API
    type_name = await get_blueprint_type_name(type_id, item_id, blueprint_cache)
    
    # Determine BPO or BPC
    bp_type = determine_blueprint_type(quantity)
    
    # Get location name from cache or API
    location_name = await get_location_name(location_id, char_id, access_token, location_cache, structure_cache, failed_structures)
    
    return type_name, location_name, bp_type

async def get_blueprint_type_name(type_id: Optional[int], item_id: int, blueprint_cache: Dict[str, Any]) -> str:
    """
    Get blueprint type name from cache or API.
    
    Args:
        type_id: The blueprint type ID
        item_id: The blueprint item ID (fallback)
        blueprint_cache: Cache for blueprint names
        
    Returns:
        The blueprint type name
    """
    if type_id:
        cached_name = get_cached_value_with_stats(blueprint_cache, str(type_id), 'blueprint')
        if cached_name:
            return cached_name
        else:
            try:
                type_data = await fetch_public_esi(f"/universe/types/{type_id}")
                if type_data:
                    type_name = type_data.get('name', f"Blueprint {item_id}").replace(" Blueprint", "").strip()
                    blueprint_cache[str(type_id)] = type_name
                    save_blueprint_cache(blueprint_cache)
                    return type_name
                else:
                    return f"Blueprint {item_id}".replace(" Blueprint", "").strip()
            except ESIRequestError as e:
                logger.error(f"Failed to fetch type data for {type_id}: {e}")
                return f"Blueprint {item_id}".replace(" Blueprint", "").strip()
    else:
        return f"Blueprint {item_id}".replace(" Blueprint", "").strip()

def determine_blueprint_type(quantity: int) -> str:
    """
    Determine if blueprint is BPO or BPC based on quantity.
    
    Args:
        quantity: Blueprint quantity (-1 for BPO, > -1 for BPC)
        
    Returns:
        "BPO" or "BPC"
    """
    return "BPO" if quantity == -1 else "BPC"

async def get_location_name(location_id: Optional[int], char_id: int, access_token: str, location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> str:
    """
    Get location name from cache or API.
    
    Args:
        location_id: The location ID
        char_id: Character ID for auth
        access_token: Access token for auth
        location_cache: Cache for location names
        structure_cache: Cache for structure names
        failed_structures: Cache for failed structure fetches
        
    Returns:
        The location name
    """
    if location_id:
        location_id_str = str(location_id)
        cached_location = get_cached_value_with_stats(location_cache, location_id_str, 'location')
        if cached_location:
            return cached_location
        elif location_id >= 1000000000000:  # Structures (citadels, etc.)
            return await get_structure_location_name(location_id, location_id_str, char_id, access_token, structure_cache, failed_structures)
        else:  # Stations - public data
            return await get_station_location_name(location_id, location_id_str, location_cache)
    else:
        return "Unknown Location"

async def get_structure_location_name(location_id: int, location_id_str: str, char_id: int, access_token: str, structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> str:
    """
    Get structure location name from cache or API.
    
    Args:
        location_id: Structure location ID
        location_id_str: String version of location ID
        char_id: Character ID for auth
        access_token: Access token
        structure_cache: Cache for structure names
        failed_structures: Cache for failed fetches
        
    Returns:
        Structure name or fallback
    """
    cached_failed = get_cached_value_with_stats(failed_structures, location_id_str, 'failed_structures')
    if cached_failed:
        return f"Citadel {location_id}"
    
    cached_structure = get_cached_value_with_stats(structure_cache, location_id_str, 'structure')
    if cached_structure:
        return cached_structure
    
    # Try auth fetch for private structures
    try:
        struct_data = await fetch_esi(f"/universe/structures/{location_id}", char_id, access_token)
        if struct_data:
            location_name = struct_data.get('name', f"Citadel {location_id}")
            structure_cache[location_id_str] = location_name
            save_structure_cache(structure_cache)
            return location_name
        else:
            location_name = f"Citadel {location_id}"
            failed_structures[location_id_str] = True
            save_failed_structures(failed_structures)
            return location_name
    except (ESIAuthError, ESIRequestError) as e:
        logger.error(f"Failed to fetch structure data for {location_id}: {e}")
        location_name = f"Citadel {location_id}"
        failed_structures[location_id_str] = True
        save_failed_structures(failed_structures)
        return location_name

async def get_station_location_name(location_id: int, location_id_str: str, location_cache: Dict[str, Any]) -> str:
    """
    Get station location name from cache or API.
    
    Args:
        location_id: Station location ID
        location_id_str: String version of location ID
        location_cache: Cache for location names
        
    Returns:
        Station name or fallback
    """
    cached_station = get_cached_value_with_stats(location_cache, location_id_str, 'location')
    if cached_station:
        return cached_station
    
    try:
        loc_data = await fetch_public_esi(f"/universe/stations/{location_id}")
        location_name = loc_data.get('name', f"Station {location_id}") if loc_data else f"Station {location_id}"
        location_cache[location_id_str] = location_name
        save_location_cache(location_cache)
        return location_name
    except ESIRequestError as e:
        logger.error(f"Failed to fetch station data for {location_id}: {e}")
        location_name = f"Station {location_id}"
        location_cache[location_id_str] = location_name
        save_location_cache(location_cache)
        return location_name

def construct_blueprint_post_data(blueprint_data: Dict[str, Any], type_name: str, location_name: str, bp_type: str, char_id: int, item_id: int) -> Dict[str, Any]:
    """
    Construct the post data dictionary for a blueprint.
    """
    me = blueprint_data.get('material_efficiency', 0)
    te = blueprint_data.get('time_efficiency', 0)
    location_id = blueprint_data.get('location_id')
    quantity = blueprint_data.get('quantity', -1)
    
    # Construct title
    title = f"{type_name} {bp_type} {me}/{te} ({location_name}) – ID: {item_id}"
    
    post_data = {
        'title': title,
        'slug': f"blueprint-{item_id}",
        'status': 'publish',
        'meta': {
            '_eve_bp_item_id': item_id,
            '_eve_bp_type_id': blueprint_data.get('type_id'),
            '_eve_bp_location_id': location_id,
            '_eve_bp_location_name': location_name,
            '_eve_bp_quantity': quantity,
            '_eve_bp_me': me,
            '_eve_bp_te': te,
            '_eve_bp_runs': blueprint_data.get('runs', -1),
            '_eve_char_id': char_id,
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }
    
    return post_data

async def fetch_character_portrait(char_id):
    """Fetch character portrait URLs from ESI."""
    endpoint = f"/characters/{char_id}/portrait/"
    return await fetch_public_esi(endpoint)