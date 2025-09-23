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
import time
import asyncio

from config import *
from api_client import fetch_public_esi, fetch_esi, wp_request, send_email, refresh_token, fetch_type_icon, sanitize_string, WordPressAuthError, WordPressRequestError, ESIAuthError, ESIRequestError, log_audit_event
from cache_manager import (
    load_blueprint_cache, save_blueprint_cache, load_blueprint_type_cache, save_blueprint_type_cache,
    load_location_cache, save_location_cache, load_structure_cache, save_structure_cache,
    load_failed_structures, save_failed_structures, load_wp_post_id_cache, save_wp_post_id_cache,
    get_cached_wp_post_id, set_cached_wp_post_id, get_cache_stats, log_cache_performance,
    get_cached_value_with_stats, flush_pending_saves
)
from fetch_data import fetch_character_portrait

logger = logging.getLogger(__name__)

def get_wp_auth():
    """Get WordPress authentication."""
    return requests.auth.HTTPBasicAuth(WP_USERNAME, WP_APP_PASSWORD)

def benchmark(func):
    async def wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        logger.info(f"{func.__name__} took {time.time() - start:.2f}s")
        return result
    return wrapper

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

async def fetch_blueprint_details(blueprint_data: Dict[str, Any], char_id: int, access_token: str, blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> Tuple[str, str, str]:
    return results

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
        logger.error(f"Failed to fetch character data for {char_id}: {e}")
        return None

def fetch_character_skills(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch character skills."""
    try:
        endpoint = f"/characters/{char_id}/skills/"
        return fetch_esi(endpoint, char_id, access_token)
    except (ESIAuthError, ESIRequestError) as e:
        logger.error(f"Failed to fetch character skills for {char_id}: {e}")
        return None

def fetch_character_blueprints(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch character blueprints."""
    try:
        endpoint = f"/characters/{char_id}/blueprints/"
        return fetch_esi(endpoint, char_id, access_token)
    except (ESIAuthError, ESIRequestError) as e:
        logger.error(f"Failed to fetch character blueprints for {char_id}: {e}")
        return None

def fetch_character_planets(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch character planets."""
    try:
        endpoint = f"/characters/{char_id}/planets/"
        return fetch_esi(endpoint, char_id, access_token)
    except (ESIAuthError, ESIRequestError) as e:
        logger.error(f"Failed to fetch character planets for {char_id}: {e}")
        return None

def fetch_corporation_data(corp_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """Fetch corporation data from ESI."""
    try:
        endpoint = f"/corporations/{corp_id}/"
        return fetch_esi(endpoint, None, access_token)  # No char_id needed for corp data
    except (ESIAuthError, ESIRequestError) as e:
        logger.error(f"Failed to fetch corporation data for {corp_id}: {e}")
        return None

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

    item_id = blueprint_data.get('item_id')
    if not item_id:
        logger.error(f"Blueprint data missing item_id: {blueprint_data}")
        return

    # Skip BPCs - only track BPOs (quantity == -1 indicates a BPO)
    quantity = blueprint_data.get('quantity', -1)
    if quantity != -1:
        logger.info(f"Skipping BPC (quantity={quantity}) for item_id: {item_id}")
        return

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

    # Fetch blueprint details
    type_name, location_name, bp_type = await fetch_blueprint_details(blueprint_data, char_id, access_token, blueprint_cache, location_cache, structure_cache, failed_structures)
    
    me = blueprint_data.get('material_efficiency', 0)
    te = blueprint_data.get('time_efficiency', 0)
    quantity = blueprint_data.get('quantity', -1)

    post_data = construct_blueprint_post_data(blueprint_data, type_name, location_name, bp_type, char_id, item_id)

    # Update or create the blueprint post in WordPress
    await update_or_create_blueprint_post(post_data, existing_post, wp_post_id_cache, item_id, blueprint_data, type_name, location_name, me, te, quantity, char_id)

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
    if type_id:
        cached_name = get_cached_value_with_stats(blueprint_cache, str(type_id))
        if cached_name:
            type_name = cached_name
        else:
            try:
                type_data = await fetch_public_esi(f"/universe/types/{type_id}")
                if type_data:
                    type_name = type_data.get('name', f"Blueprint {item_id}").replace(" Blueprint", "").strip()
                    blueprint_cache[str(type_id)] = type_name
                    save_blueprint_cache(blueprint_cache)
                else:
                    type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()
            except ESIRequestError as e:
                logger.error(f"Failed to fetch type data for {type_id}: {e}")
                type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()
    else:
        type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()

    # Determine BPO or BPC
    bp_type = "BPO" if quantity == -1 else "BPC"

    # Get location name from cache or API
    if location_id:
        location_id_str = str(location_id)
        cached_location = get_cached_value_with_stats(location_cache, location_id_str)
        if cached_location:
            location_name = cached_location
        elif location_id >= 1000000000000:  # Structures (citadels, etc.)
            cached_failed = get_cached_value_with_stats(failed_structures, location_id_str)
            if cached_failed:
                location_name = f"Citadel {location_id}"
            else:
                cached_structure = get_cached_value_with_stats(structure_cache, location_id_str)
                if cached_structure:
                    location_name = cached_structure
                else:
                    # Try auth fetch for private structures
                    try:
                        struct_data = await fetch_esi(f"/universe/structures/{location_id}", char_id, access_token)
                        if struct_data:
                            location_name = struct_data.get('name', f"Citadel {location_id}")
                            structure_cache[location_id_str] = location_name
                            save_structure_cache(structure_cache)
                        else:
                            location_name = f"Citadel {location_id}"
                            failed_structures[location_id_str] = True
                            save_failed_structures(failed_structures)
                    except (ESIAuthError, ESIRequestError) as e:
                        logger.error(f"Failed to fetch structure data for {location_id}: {e}")
                        location_name = f"Citadel {location_id}"
                        failed_structures[location_id_str] = True
                        save_failed_structures(failed_structures)
        else:  # Stations - public data
            cached_station = get_cached_value_with_stats(location_cache, location_id_str)
            if cached_station:
                location_name = cached_station
            else:
                try:
                    loc_data = await fetch_public_esi(f"/universe/stations/{location_id}")
                    location_name = loc_data.get('name', f"Station {location_id}") if loc_data else f"Station {location_id}"
                    location_cache[location_id_str] = location_name
                    save_location_cache(location_cache)
                except ESIRequestError as e:
                    logger.error(f"Failed to fetch station data for {location_id}: {e}")
                    location_name = f"Station {location_id}"
                    location_cache[location_id_str] = location_name
                    save_location_cache(location_cache)
    else:
        location_name = "Unknown Location"
    
    return type_name, location_name, bp_type

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