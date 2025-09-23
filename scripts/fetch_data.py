#!/usr/bin/env python3
"""
EVE Observer Data Fetcher
Fetches data from EVE ESI API and stores in WordPress database via REST API.
"""

import os
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
import logging
import argparse
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
from config import *
from esi_oauth import save_tokens
from blueprint_processor import (
    update_blueprint_in_wp, extract_blueprints_from_assets, extract_blueprints_from_industry_jobs,
    extract_blueprints_from_contracts, update_blueprint_from_asset_in_wp
)
from character_processor import update_character_skills_in_wp, check_industry_job_completions, update_planet_in_wp
from corporation_processor import update_corporation_in_wp
from data_processors import fetch_character_data, update_character_in_wp
class ESIApiError(Exception):
    """Base exception for ESI API errors."""
    pass

class ESIAuthError(ESIApiError):
    """Exception raised for authentication failures."""
    pass

class ESIRequestError(ESIApiError):
    """Exception raised for general ESI request errors."""
    pass

@dataclass
class ApiConfig:
    """Centralized configuration for API settings and limits."""
    esi_base_url: str = 'https://esi.evetech.net/latest'
    esi_timeout: int = 30
    esi_max_retries: int = 3
    esi_max_workers: int = 10
    wp_per_page: int = 100
    rate_limit_buffer: int = 1
    
    @classmethod
    def from_env(cls) -> 'ApiConfig':
        """Create ApiConfig instance from environment variables."""
        return cls(
            esi_base_url=os.getenv('ESI_BASE_URL', 'https://esi.evetech.net/latest'),
            esi_timeout=int(os.getenv('ESI_TIMEOUT', 30)),
            esi_max_retries=int(os.getenv('ESI_MAX_RETRIES', 3)),
            esi_max_workers=int(os.getenv('ESI_MAX_WORKERS', 10)),
            wp_per_page=int(os.getenv('WP_PER_PAGE', 100)),
        )

load_dotenv()

# Create a global aiohttp session for connection reuse
session = None

async def get_session():
    """
    Get or create a global aiohttp ClientSession for connection reuse.

    Creates a new session with configured timeout and connection limits if one
    doesn't exist or has been closed. Uses TCPConnector with worker limits to
    prevent connection pool exhaustion.

    Returns:
        aiohttp.ClientSession: The global session instance for HTTP requests.
    """
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=api_config.esi_timeout),
            connector=aiohttp.TCPConnector(limit=api_config.esi_max_workers * 2)
        )
    return session

# Initialize API configuration
api_config = ApiConfig.from_env()

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
# WordPress post ID cache
WP_POST_ID_CACHE_FILE = os.path.join(CACHE_DIR, 'wp_post_ids.json')

def load_tokens() -> Dict[str, Any]:
    """
    Load stored OAuth2 tokens from the tokens file.

    Reads the ESI tokens file containing access tokens, refresh tokens, and
    expiration data for authorized characters.

    Returns:
        Dict[str, Any]: Dictionary of token data keyed by character ID.
                       Empty dict if file doesn't exist or can't be read.
    """
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return {}

def ensure_cache_dir() -> None:
    """
    Ensure the cache directory exists, creating it if necessary.

    Creates the configured cache directory and any parent directories
    needed to store cache files for blueprints, locations, structures, etc.
    """
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def load_cache(cache_file: str) -> Dict[str, Any]:
    """
    Load cached data from a JSON file.

    Attempts to read and parse a JSON cache file. Creates the cache directory
    if it doesn't exist. Returns empty dict if file doesn't exist or is invalid.

    Args:
        cache_file: Path to the cache file to load.

    Returns:
        Dict[str, Any]: Cached data dictionary, or empty dict on error.
    """
    ensure_cache_dir()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache_file: str, data: Dict[str, Any]) -> None:
    """
    Save data to a JSON cache file.

    Writes the provided data dictionary to a JSON file, creating the cache
    directory if needed. Used for persisting blueprint names, location data, etc.

    Args:
        cache_file: Path to the cache file to save.
        data: Dictionary data to save as JSON.
    """
    ensure_cache_dir()
    with open(cache_file, 'w') as f:
        json.dump(data, f)

def load_blueprint_cache() -> Dict[str, Any]:
    """
    Load the blueprint name cache.

    Retrieves cached blueprint type names keyed by type_id to avoid
    repeated ESI API calls for blueprint name resolution.

    Returns:
        Dict[str, Any]: Blueprint name cache dictionary.
    """
    return load_cache(BLUEPRINT_CACHE_FILE)

def save_blueprint_cache(cache: Dict[str, Any]) -> None:
    """
    Save the blueprint name cache to disk.

    Persists the blueprint name cache to improve performance on subsequent runs
    by avoiding repeated API calls for blueprint type name resolution.

    Args:
        cache: Blueprint name cache dictionary to save.
    """
    save_cache(BLUEPRINT_CACHE_FILE, cache)

def load_blueprint_type_cache() -> Dict[str, Any]:
    """
    Load the blueprint type classification cache.

    Retrieves cached information about which type_ids represent blueprints
    vs regular items, used for filtering contract items.

    Returns:
        Dict[str, Any]: Blueprint type cache dictionary.
    """
    return load_cache(BLUEPRINT_TYPE_CACHE_FILE)

def save_blueprint_type_cache(cache: Dict[str, Any]) -> None:
    """
    Save the blueprint type classification cache.

    Persists blueprint type information to avoid repeated API calls
    when determining if items in contracts are blueprints.

    Args:
        cache: Blueprint type cache dictionary to save.
    """
    save_cache(BLUEPRINT_TYPE_CACHE_FILE, cache)

def load_location_cache() -> Dict[str, Any]:
    """
    Load the location name cache.

    Retrieves cached station names keyed by location_id to avoid
    repeated ESI API calls for location name resolution.

    Returns:
        Dict[str, Any]: Location name cache dictionary.
    """
    return load_cache(LOCATION_CACHE_FILE)

def save_location_cache(cache: Dict[str, Any]) -> None:
    """
    Save the location name cache to disk.

    Persists location name cache to improve performance by avoiding
    repeated API calls for station/structure name resolution.

    Args:
        cache: Location name cache dictionary to save.
    """
    save_cache(LOCATION_CACHE_FILE, cache)

def load_structure_cache() -> Dict[str, Any]:
    """
    Load the structure name cache.

    Retrieves cached citadel/structure names keyed by location_id.
    Used for resolving player-owned structure names.

    Returns:
        Dict[str, Any]: Structure name cache dictionary.
    """
    return load_cache(STRUCTURE_CACHE_FILE)

def save_structure_cache(cache: Dict[str, Any]) -> None:
    """
    Save the structure name cache to disk.

    Persists structure name cache for citadels and player-owned structures
    to avoid repeated authenticated API calls.

    Args:
        cache: Structure name cache dictionary to save.
    """
    save_cache(STRUCTURE_CACHE_FILE, cache)

def load_failed_structures() -> Dict[str, Any]:
    """
    Load the failed structures cache.

    Retrieves cache of structure IDs that previously failed to resolve,
    avoiding repeated attempts to fetch inaccessible citadel names.

    Returns:
        Dict[str, Any]: Failed structures cache dictionary.
    """
    return load_cache(FAILED_STRUCTURES_FILE)

def load_wp_post_id_cache() -> Dict[str, Any]:
    """
    Load the WordPress post ID cache.

    Retrieves cached WordPress post IDs keyed by post type and item ID
    to avoid repeated slug lookups when updating existing posts.

    Returns:
        Dict[str, Any]: WordPress post ID cache dictionary.
    """
    return load_cache(WP_POST_ID_CACHE_FILE)

def save_wp_post_id_cache(cache: Dict[str, Any]) -> None:
    """
    Save the WordPress post ID cache to disk.

    Persists WordPress post ID mappings to improve update performance
    by avoiding repeated API calls to find existing posts by slug.

    Args:
        cache: WordPress post ID cache dictionary to save.
    """
    save_cache(WP_POST_ID_CACHE_FILE, cache)

def get_cached_wp_post_id(cache: Dict[str, Any], post_type: str, item_id: int) -> Optional[int]:
    """
    Get a cached WordPress post ID for an item.

    Retrieves the WordPress post ID from cache using a composite key
    of post_type and item_id to avoid API calls when updating posts.

    Args:
        cache: WordPress post ID cache dictionary.
        post_type: WordPress custom post type (e.g., 'eve_blueprint').
        item_id: EVE item/entity ID.

    Returns:
        Optional[int]: Cached post ID if found, None otherwise.
    """
    key = f"{post_type}_{item_id}"
    return cache.get(key)

def set_cached_wp_post_id(cache: Dict[str, Any], post_type: str, item_id: int, post_id: int) -> None:
    """
    Cache a WordPress post ID for an item.

    Stores the WordPress post ID in cache using a composite key for fast
    lookups when updating existing posts.

    Args:
        cache: WordPress post ID cache dictionary to update.
        post_type: WordPress custom post type (e.g., 'eve_blueprint').
        item_id: EVE item/entity ID.
        post_id: WordPress post ID to cache.
    """
    key = f"{post_type}_{item_id}"
    cache[key] = post_id
    save_wp_post_id_cache(cache)



def send_email(subject: str, body: str) -> None:
    """
    Send an email alert using configured SMTP settings.

    Sends email notifications for system alerts, errors, or important events.
    Requires complete email configuration (SMTP server, credentials, addresses).

    Args:
        subject: Email subject line.
        body: Email body content (plain text).

    Note:
        Silently skips sending if email configuration is incomplete.
        Uses SMTP with STARTTLS for secure delivery.
    """
    if not all([EMAIL_SMTP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO]):
        logger.warning("Email configuration incomplete, skipping alert.")
        return

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO

    try:
        server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        server.quit()
        logger.info(f"Alert email sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

async def fetch_public_esi(endpoint: str, max_retries: int = None) -> Optional[Dict[str, Any]]:
    """
    Fetch data from ESI API public endpoints with rate limiting and error handling.

    Makes HTTP GET requests to public ESI endpoints (no authentication required).
    Implements comprehensive error handling including rate limiting, retries with
    exponential backoff, and proper handling of ESI error headers.

    Args:
        endpoint: ESI API endpoint path (e.g., '/universe/types/123').
        max_retries: Maximum number of retry attempts (uses config default if None).

    Returns:
        Optional[Dict[str, Any]]: JSON response data if successful, None on failure.

    Note:
        Handles ESI rate limiting by respecting X-ESI-Error-Limit-Remain and
        X-ESI-Error-Limit-Reset headers. Uses exponential backoff for retries.
    """
    if max_retries is None:
        max_retries = api_config.esi_max_retries
    
    import time

    sess = await get_session()
    url = f"{api_config.esi_base_url}{endpoint}"

    for attempt in range(max_retries):
        try:
            async with sess.get(url) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    logger.warning(f"Resource not found for public endpoint {endpoint}")
                    return None
                elif response.status == 429:  # Rate limited
                    # Check for X-ESI-Error-Limit-Remain header
                    error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                    error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                    if error_limit_reset:
                        wait_time = int(error_limit_reset) + 1  # Add 1 second buffer
                        logger.info(f"RATE LIMIT: Waiting {wait_time} seconds for public endpoint...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # Fallback: wait 60 seconds if no reset header
                        logger.info(f"RATE LIMIT: Waiting 60 seconds for public endpoint (no reset header)...")
                        await asyncio.sleep(60)
                        continue
                elif response.status == 420:  # Error limited
                    error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                    error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                    if error_limit_reset:
                        wait_time = int(error_limit_reset) + 1
                        logger.info(f"ERROR LIMIT: Waiting {wait_time} seconds for public endpoint...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.info(f"ERROR LIMIT: Waiting 60 seconds for public endpoint...")
                        await asyncio.sleep(60)
                        continue
                elif response.status >= 500:
                    # Server error, retry
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(f"SERVER ERROR {response.status}: Retrying in {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"SERVER ERROR {response.status}: Max retries exceeded")
                        return None
                else:
                    logger.error(f"ESI API error for {endpoint}: {response.status} - {await response.text()}")
                    return None

        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"TIMEOUT: Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error("TIMEOUT: Max retries exceeded")
                return None
        except aiohttp.ClientError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"NETWORK ERROR: {e}. Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"NETWORK ERROR: {e}. Max retries exceeded")
                return None

    return None

async def fetch_esi(endpoint: str, char_id: Optional[int], access_token: str, max_retries: int = None) -> Optional[Dict[str, Any]]:
    """
    Fetch data from ESI API authenticated endpoints with rate limiting and error handling.

    Makes authenticated HTTP GET requests to ESI endpoints requiring OAuth2 tokens.
    Implements comprehensive error handling for auth failures, rate limiting, and
    network issues with automatic retries and exponential backoff.

    Args:
        endpoint: ESI API endpoint path (e.g., '/characters/123/skills/').
        char_id: Character ID for authentication context (can be None for corp endpoints).
        access_token: Valid OAuth2 access token for ESI authentication.
        max_retries: Maximum number of retry attempts (uses config default if None).

    Returns:
        Optional[Dict[str, Any]]: JSON response data if successful, None on failure.

    Note:
        Handles authentication errors (401/403), rate limiting, and server errors.
        Uses Bearer token authentication in Authorization header.
    """
    if max_retries is None:
        max_retries = api_config.esi_max_retries
    
    import time

    sess = await get_session()
    url = f"{api_config.esi_base_url}{endpoint}"
    headers = {'Authorization': f'Bearer {access_token}'}

    for attempt in range(max_retries):
        try:
            async with sess.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    logger.error(f"Authentication failed for endpoint {endpoint}")
                    return None
                elif response.status == 403:
                    logger.error(f"Access forbidden for endpoint {endpoint}")
                    return None
                elif response.status == 404:
                    logger.warning(f"Resource not found for endpoint {endpoint}")
                    return None
                elif response.status == 429:  # Rate limited
                    # Check for X-ESI-Error-Limit-Remain header
                    error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                    error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                    if error_limit_reset:
                        wait_time = int(error_limit_reset) + 1  # Add 1 second buffer
                        logger.info(f"RATE LIMIT: Waiting {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        # Fallback: wait 60 seconds if no reset header
                        logger.info(f"RATE LIMIT: Waiting 60 seconds (no reset header)...")
                        await asyncio.sleep(60)
                        continue
                elif response.status == 420:  # Error limited
                    error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                    error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                    if error_limit_reset:
                        wait_time = int(error_limit_reset) + 1
                        logger.info(f"ERROR LIMIT: Waiting {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.info(f"ERROR LIMIT: Waiting 60 seconds...")
                        await asyncio.sleep(60)
                        continue
                elif response.status >= 500:
                    # Server error, retry
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(f"SERVER ERROR {response.status}: Retrying in {wait_time} seconds...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"SERVER ERROR {response.status}: Max retries exceeded")
                        return None
                else:
                    logger.error(f"ESI API error for {endpoint}: {response.status} - {await response.text()}")
                    return None

        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"TIMEOUT: Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error("TIMEOUT: Max retries exceeded")
                return None
        except aiohttp.ClientError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"NETWORK ERROR: {e}. Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"NETWORK ERROR: {e}. Max retries exceeded")
                return None

    return None

async def wp_request(method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
    """
    Make an asynchronous request to the WordPress REST API.

    Performs HTTP requests to WordPress with Basic Authentication for
    creating, reading, updating, or deleting custom post types.

    Args:
        method: HTTP method ('GET', 'POST', 'PUT', 'DELETE').
        endpoint: WordPress API endpoint path.
        data: Request payload for POST/PUT requests.

    Returns:
        Optional[Dict]: JSON response data if successful, None on error.

    Note:
        Uses Basic Auth with configured WordPress credentials.
        DELETE requests support optional 'force' parameter in data.
    """
    sess = await get_session()
    url = f"{WP_BASE_URL}{endpoint}"
    auth = aiohttp.BasicAuth(WP_USERNAME, WP_APP_PASSWORD)
    
    try:
        if method.upper() == 'GET':
            async with sess.get(url, auth=auth) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"WordPress API error: {response.status} - {await response.text()}")
                    return None
        elif method.upper() == 'POST':
            async with sess.post(url, json=data, auth=auth) as response:
                if response.status in [200, 201]:
                    return await response.json()
                else:
                    logger.error(f"WordPress API error: {response.status} - {await response.text()}")
                    return None
        elif method.upper() == 'PUT':
            async with sess.put(url, json=data, auth=auth) as response:
                if response.status in [200, 201]:
                    return await response.json()
                else:
                    logger.error(f"WordPress API error: {response.status} - {await response.text()}")
                    return None
        elif method.upper() == 'DELETE':
            params = {'force': 'true'} if data and data.get('force') else None
            async with sess.delete(url, auth=auth, params=params) as response:
                return response.status == 200
    except Exception as e:
        logger.error(f"WordPress API request failed: {e}")
        return None
    
    return None

async def fetch_character_skills(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch character skills and training information from ESI.

    Retrieves the character's skill queue, trained skills, and total skill points.
    Used for tracking character progression and skill training status.

    Args:
        char_id: EVE character ID to fetch skills for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Skills data including total_sp and skills array.
    """
    endpoint = f"/characters/{char_id}/skills/"
    return await fetch_esi(endpoint, char_id, access_token)

async def fetch_character_blueprints(char_id, access_token):
    """
    Fetch character blueprint collection from ESI.

    Retrieves all blueprints owned by the character, including both BPOs and BPCs,
    with their ME/TE levels, location, and other blueprint attributes.

    Args:
        char_id: EVE character ID to fetch blueprints for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Blueprint data array if successful.
    """
    endpoint = f"/characters/{char_id}/blueprints/"
    return await fetch_esi(endpoint, char_id, access_token)

async def fetch_character_planets(char_id, access_token):
    """
    Fetch character planetary colony information from ESI.

    Retrieves data about the character's planetary colonies (PI), including
    planet types, colony status, and resource extraction setups.

    Args:
        char_id: EVE character ID to fetch planets for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Planetary colony data array if successful.
    """
    endpoint = f"/characters/{char_id}/planets/"
    return await fetch_esi(endpoint, char_id, access_token)

async def fetch_corporation_data(corp_id, access_token):
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

async def fetch_character_assets(char_id, access_token):
    """
    Fetch character assets from ESI.

    Retrieves the complete list of items owned by the character across all locations,
    including items in stations, structures, and ships.

    Args:
        char_id: EVE character ID to fetch assets for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Assets data array if successful.
    """
    endpoint = f"/characters/{char_id}/assets/"
    return await fetch_esi(endpoint, char_id, access_token)

async def fetch_character_contracts(char_id, access_token):
    """
    Fetch character contracts from ESI.

    Retrieves all contracts the character is involved in, including contracts
    they've issued, accepted, or have access to.

    Args:
        char_id: EVE character ID to fetch contracts for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Contracts data array if successful.
    """
    endpoint = f"/characters/{char_id}/contracts/"
    return await fetch_esi(endpoint, char_id, access_token)

def fetch_character_contract_items(char_id, contract_id, access_token):
    """
    Fetch items in a specific character contract from ESI.

    Retrieves the detailed list of items included in a particular contract,
    including quantities and types for contract analysis.

    Args:
        char_id: EVE character ID that owns the contract.
        contract_id: Specific contract ID to fetch items for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Contract items data array if successful.
    """
    endpoint = f"/characters/{char_id}/contracts/{contract_id}/items/"
    return fetch_esi(endpoint, char_id, access_token)

async def fetch_corporation_blueprints(corp_id, access_token):
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

async def fetch_corporation_contracts(corp_id, access_token):
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

def fetch_corporation_contract_items(corp_id, contract_id, access_token):
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

async def fetch_corporation_industry_jobs(corp_id, access_token):
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


async def fetch_character_industry_jobs(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch character industry jobs from ESI.

    Retrieves all active industry jobs for the character, including manufacturing,
    research, and other industry activities.

    Args:
        char_id: EVE character ID to fetch industry jobs for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Industry jobs data array if successful.
    """
    endpoint = f"/characters/{char_id}/industry/jobs/"
    return await fetch_esi(endpoint, char_id, access_token)

async def fetch_corporation_assets(corp_id, access_token):
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

def generate_contract_title(contract_data, for_corp=False, entity_id=None, contract_items=None, blueprint_cache=None):
    """
    Generate a descriptive contract title based on contract items.

    Creates human-readable contract titles by analyzing the items included
    in the contract, with special handling for blueprint contracts.

    Args:
        contract_data: Contract data dictionary from ESI API.
        for_corp: Whether this is a corporation contract.
        entity_id: Character or corporation ID for context.
        contract_items: List of items in the contract.
        blueprint_cache: Cache for blueprint type information.

    Returns:
        str: Descriptive contract title.

    Note:
        Titles follow format: "[Corp] {item_description} - Contract {id}"
        or fallback to "Contract {id} - {type} ({status})"
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
                    # Double-check with ESI if not in cache
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

def get_region_from_location(location_id):
    """
    Get region_id from a location_id (station or structure) with caching.

    Resolves location IDs to region IDs by traversing the EVE universe hierarchy:
    location -> solar system -> constellation -> region.

    Args:
        location_id: Station or structure location ID.

    Returns:
        Optional[int]: Region ID if found, None otherwise.

    Note:
        Uses caching to avoid repeated API calls. Handles both station
        and structure location types differently.
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
    import requests
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

async def fetch_corporation_logo(corp_id):
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

async def fetch_planet_details(char_id, planet_id, access_token):
    """
    Fetch detailed planetary colony information from ESI.

    Retrieves detailed information about a specific planetary colony,
    including resource extraction, factory setups, and colony status.

    Args:
        char_id: EVE character ID that owns the colony.
        planet_id: Specific planet ID to fetch details for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Detailed planet colony data if successful.
    """
    endpoint = f"/characters/{char_id}/planets/{planet_id}/"
    return await fetch_esi(endpoint, char_id, access_token) 
def refresh_token(refresh_token):
    """
    Refresh an expired OAuth2 access token.

    Exchanges a refresh token for a new access token using EVE's OAuth2 endpoint.
    Updates the token's expiration time based on the response.

    Args:
        refresh_token: The refresh token to exchange.

    Returns:
        Optional[Dict[str, Any]]: Updated token data with new access_token,
                                 refresh_token, and expires_at, or None on failure.

    Note:
        Requires ESI_CLIENT_ID and ESI_CLIENT_SECRET environment variables.
    """
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    client_id = os.getenv('ESI_CLIENT_ID')
    client_secret = os.getenv('ESI_CLIENT_SECRET')
    response = requests.post('https://login.eveonline.com/v2/oauth/token', data=data, auth=(client_id, client_secret))
    if response.status_code == 200:
        token_data = response.json()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data['expires_in'])
        return {
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token', refresh_token),
            'expires_at': expires_at.isoformat()
        }
    else:
        logger.error(f"Failed to refresh token: {response.status_code} - {response.text}")
        return None

def fetch_public_contract_items(contract_id, max_retries=3):
    """
    Fetch items in a public contract with retry logic.

    Retrieves the detailed list of items included in a public contract,
    with built-in retry logic and rate limit monitoring.

    Args:
        contract_id: Public contract ID to fetch items for.
        max_retries: Maximum number of retry attempts (default 3).

    Returns:
        Optional[Dict[str, Any]]: Contract items data array if successful.

    Note:
        Monitors ESI rate limits and logs warnings when approaching limits.
        Uses exponential backoff for retries.
    """
    endpoint = f"/contracts/public/items/{contract_id}/"
    import requests
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

async def collect_corporation_members(tokens):
    """
    Collect all corporations and their member characters from authorized tokens.

    Groups authorized characters by their corporation membership, refreshing
    expired tokens as needed and updating character data in WordPress.

    Args:
        tokens: Dictionary of token data keyed by character ID.

    Returns:
        Dict[int, List[Tuple[int, str, str]]]: Corporation members grouped by corp_id,
                                               each member as (char_id, access_token, char_name).

    Note:
        Automatically refreshes expired tokens and updates token storage.
        Updates character posts in WordPress with latest data.
    """
    corp_members = {}
    for char_id, token_data in tokens.items():
        try:
            expired = datetime.now(timezone.utc) > datetime.fromisoformat(token_data.get('expires_at', '2000-01-01T00:00:00+00:00'))
        except:
            expired = True
        if expired:
            new_token = refresh_token(token_data['refresh_token'])
            if new_token:
                token_data.update(new_token)
                save_tokens(tokens)
            else:
                logger.warning(f"Failed to refresh token for {token_data['name']}")
                continue

        access_token = token_data['access_token']
        char_name = token_data['name']

        # Fetch basic character data to get corporation
        char_data = await fetch_character_data(char_id, access_token)
        if char_data:
            await update_character_in_wp(char_id, char_data)
            corp_id = char_data.get('corporation_id')
            if corp_id:
                if corp_id not in corp_members:
                    corp_members[corp_id] = []
                corp_members[corp_id].append((char_id, access_token, char_name))

    return corp_members

def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments for the data fetching script.

    Supports selective data fetching by type or fetching all data types.
    Defaults to fetching all data if no specific flags are provided.

    Returns:
        argparse.Namespace: Parsed command line arguments.

    Options:
        --contracts: Fetch contract data
        --planets: Fetch planetary colony data
        --blueprints: Fetch blueprint data
        --skills: Fetch character skills data
        --corporations: Fetch corporation data
        --characters: Fetch character data
        --all: Fetch all data types (default)
    """
    parser = argparse.ArgumentParser(description='Fetch EVE Online data from ESI API')
    parser.add_argument('--contracts', action='store_true', help='Fetch contracts data')
    parser.add_argument('--planets', action='store_true', help='Fetch planets data')
    parser.add_argument('--blueprints', action='store_true', help='Fetch blueprints data')
    parser.add_argument('--skills', action='store_true', help='Fetch skills data')
    parser.add_argument('--corporations', action='store_true', help='Fetch corporation data')
    parser.add_argument('--characters', action='store_true', help='Fetch character data')
    parser.add_argument('--all', action='store_true', help='Fetch all data (default)')
    
    args = parser.parse_args()
    
    # If no specific flags set, default to --all
    if not any([args.contracts, args.planets, args.blueprints, args.skills, args.corporations, args.characters]):
        args.all = True
    
    return args

def clear_log_file() -> None:
    """
    Clear the log file at the start of each run.

    Truncates the log file to ensure clean logging output for each execution,
    preventing log files from growing indefinitely.
    """
    with open(LOG_FILE, 'w') as f:
        f.truncate(0)

def initialize_caches() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Load all caches at the beginning of execution.

    Initializes all cache dictionaries from disk to improve performance
    by avoiding repeated API calls for blueprint names, locations, etc.

    Returns:
        Tuple[Dict[str, Any], ...]: Tuple of cache dictionaries in order:
                                   (blueprint_cache, location_cache, structure_cache,
                                    failed_structures, wp_post_id_cache)
    """
    blueprint_cache = load_blueprint_cache()
    location_cache = load_location_cache()
    structure_cache = load_structure_cache()
    failed_structures = load_failed_structures()
    wp_post_id_cache = load_wp_post_id_cache()
    return blueprint_cache, location_cache, structure_cache, failed_structures, wp_post_id_cache

def get_allowed_entities(corp_members: Dict[int, List[Tuple[int, str, str]]]) -> Tuple[set, set]:
    """
    Define allowed corporations and issuers for contract filtering.

    Creates sets of allowed corporation IDs and character IDs for filtering
    contract data to only include relevant entities.

    Args:
        corp_members: Corporation members grouped by corporation ID.

    Returns:
        Tuple[set, set]: (allowed_corp_ids, allowed_issuer_ids)

    Note:
        Currently hardcoded to allow No Mercy Incorporated (corp_id: 98092220)
        and its members for contract processing.
    """
    allowed_corp_ids = {98092220}  # No Mercy Incorporated
    allowed_issuer_ids = {
        char_id for corp_id, members in corp_members.items()
        if corp_id == 98092220  # No Mercy Incorporated
        for char_id, access_token, char_name in members
    }
    return allowed_corp_ids, allowed_issuer_ids

async def process_all_data(corp_members: Dict[int, List[Tuple[int, str, str]]], caches: Tuple[Dict[str, Any], ...], args: argparse.Namespace, tokens: Dict[str, Any]) -> None:
    """
    Process all corporation and character data based on command line arguments.

    Orchestrates the fetching and processing of data for all authorized corporations
    and their member characters, respecting the selected data types.

    Args:
        corp_members: Corporation members grouped by corporation ID.
        caches: Tuple of cache dictionaries.
        args: Parsed command line arguments.
        tokens: Dictionary of token data keyed by character ID.

    Note:
        Processes corporations first, then individual characters.
        Only processes corporations in the ALLOWED_CORPORATIONS list.
    """
    blueprint_cache, location_cache, structure_cache, failed_structures, wp_post_id_cache = caches
    
    # Process each corporation with any available member token
    processed_corps = set()
    for corp_id, members in corp_members.items():
        if corp_id in processed_corps:
            continue

        # Process data for the corporation and its members
        if args.all or args.corporations or args.blueprints:
            await process_corporation_data(corp_id, members, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures, args)

        processed_corps.add(corp_id)

    # Now process individual character data (skills, blueprints, etc.)
    for char_id, token_data in tokens.items():
        if args.all or args.characters or args.skills or args.blueprints or args.planets or args.contracts:
            await process_character_data(char_id, token_data, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures, args)

async def main() -> None:
    """
    Main data fetching routine.

    Orchestrates the complete data fetching and processing workflow:
    - Parse command line arguments
    - Clear log file
    - Load caches and tokens
    - Collect corporation members
    - Clean up old posts (if doing full fetch)
    - Process all data according to arguments

    Raises:
        SystemExit: If no authorized characters are found.
    """
    args = parse_arguments()
    clear_log_file()
    caches = initialize_caches()
    tokens = load_tokens()
    if not tokens:
        logger.error("No authorized characters found. Run 'python esi_oauth.py authorize' first.")
        return

    # Collect all corporations and their member characters
    corp_members = await collect_corporation_members(tokens)
    allowed_corp_ids, allowed_issuer_ids = get_allowed_entities(corp_members)

    # Clean up old posts with filtering (only if doing full fetch or contracts)
    if args.all or args.contracts:
        cleanup_old_posts(allowed_corp_ids, allowed_issuer_ids)

    await process_all_data(corp_members, caches, args, tokens)

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


async def process_corporation_data(corp_id, members, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures, args):
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


async def process_corporation_blueprints(corp_id, access_token, char_id, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures):
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

async def process_corporation_contracts(corp_id, access_token, corp_data, blueprint_cache):
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

async def process_character_skills(char_id: int, access_token: str, char_name: str) -> None:
    """
    Process character skills data.

    Fetches character skills and total SP, then updates the character post
    in WordPress with the latest skills information.

    Args:
        char_id: Character ID to process skills for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
    """
    skills = await fetch_character_skills(char_id, access_token)
    if skills:
        # Update character with skills data
        update_character_skills_in_wp(char_id, skills)
        logger.info(f"Skills for {char_name}: {skills['total_sp']} SP")


async def process_character_planets(char_id: int, access_token: str, char_name: str) -> None:
    """
    Process character planetary colony data.

    Fetches planetary colonies and retrieves detailed information for each,
    then updates planet posts in WordPress.

    Args:
        char_id: Character ID to process planets for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
    """
    planets = await fetch_character_planets(char_id, access_token)
    if planets:
        logger.info(f"Planets for {char_name}: {len(planets)} colonies")
        for planet in planets:
            planet_id = planet.get('planet_id')
            if planet_id:
                planet_details = await fetch_planet_details(char_id, planet_id, access_token)
                if planet_details:
                    update_planet_in_wp(char_id, planet_id, planet_details)


async def process_character_data(char_id, token_data, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures, args):
    """
    Process data for a single character.

    Fetches and processes character-specific data including skills, blueprints
    from multiple sources, planetary colonies, and contracts.

    Args:
        char_id: Character ID to process.
        token_data: Token data dictionary for the character.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
        args: Parsed command line arguments.
    """
    access_token = token_data['access_token']
    char_name = token_data['name']

    logger.info(f"Fetching additional data for {char_name}...")

    # Fetch skills
    if args.all or args.skills:
        await process_character_skills(char_id, access_token, char_name)

    # Process character blueprints from all sources
    if args.all or args.blueprints:
        await process_character_blueprints(char_id, access_token, char_name, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures)

    # Process character planets
    if args.all or args.planets:
        await process_character_planets(char_id, access_token, char_name)

    # Process character contracts
    if args.all or args.contracts:
        await process_character_contracts(char_id, access_token, char_name, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures)

async def process_character_blueprints_from_endpoint(char_id: int, access_token: str, char_name: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process character blueprints from the direct blueprints endpoint.

    Fetches blueprints directly from the character's blueprint endpoint,
    filters to BPOs only, and processes them in parallel.

    Args:
        char_id: Character ID to fetch blueprints for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    logger.info(f"Fetching blueprints for {char_name}...")
    
    blueprints = await fetch_character_blueprints(char_id, access_token)
    if blueprints:
        # Filter to only BPOs (quantity == -1)
        bpo_blueprints = [bp for bp in blueprints if bp.get('quantity', 1) == -1]
        logger.info(f"Character blueprints: {len(blueprints)} total, {len(bpo_blueprints)} BPOs")
        if bpo_blueprints:
            # Process blueprints in parallel
            await process_blueprints_parallel(
                bpo_blueprints,
                update_blueprint_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )


async def process_character_blueprints_from_assets(char_id: int, access_token: str, char_name: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process character blueprints from character assets.

    Extracts blueprints from character asset lists and processes them.

    Args:
        char_id: Character ID to fetch assets for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    char_assets = await fetch_character_assets(char_id, access_token)
    if char_assets:
        asset_blueprints = extract_blueprints_from_assets(char_assets, 'char', char_id, access_token)
        if asset_blueprints:
            logger.info(f"Character asset blueprints: {len(asset_blueprints)} items")
            # Process blueprints in parallel
            await process_blueprints_parallel(
                asset_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )


async def process_character_blueprints_from_industry_jobs(char_id: int, access_token: str, char_name: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process character blueprints from character industry jobs.

    Extracts blueprints from active character industry jobs and processes them.

    Args:
        char_id: Character ID to fetch industry jobs for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    jobs = await fetch_character_industry_jobs(char_id, access_token)
    if jobs:
        logger.info(f"Industry jobs for {char_name}: {len(jobs)} active")
        job_blueprints = extract_blueprints_from_industry_jobs(jobs, 'char', char_id)
        if job_blueprints:
            logger.info(f"Character industry job blueprints: {len(job_blueprints)} items")
            # Process blueprints in parallel
            await process_blueprints_parallel(
                job_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

async def process_character_contracts(char_id: int, access_token: str, char_name: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
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
        contract_blueprints = extract_blueprints_from_contracts(char_contracts, 'char', char_id)
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
                failed_structures
            )

        # Process contracts themselves
        for contract in char_contracts:
            contract_status = contract.get('status', '')
            if contract_status in ['finished', 'deleted']:
                # Skip finished/deleted contracts to improve performance
                continue
            elif contract_status == 'expired':
                logger.info(f"EXPIRED CHARACTER CONTRACT TO DELETE MANUALLY: {contract['contract_id']}")
            update_contract_in_wp(contract['contract_id'], contract, for_corp=False, entity_id=char_id, access_token=access_token, blueprint_cache=blueprint_cache)


async def fetch_type_icon(type_id, size=512):
    """
    Fetch type icon URL from images.evetech.net with fallback.

    Attempts to fetch blueprint-specific icons first, then falls back to
    regular item icons. Tests URL availability before returning.

    Args:
        type_id: EVE type ID to fetch icon for.
        size: Icon size in pixels (default 512).

    Returns:
        str: Icon URL if available, placeholder URL otherwise.

    Note:
        Tests icon availability with HEAD requests to avoid broken images.
    """
    # Try the 'bp' variation first for blueprints, then fallback to regular icon
    variations = ['bp', 'icon']
    
    sess = await get_session()
    for variation in variations:
        icon_url = f"https://images.evetech.net/types/{type_id}/{variation}?size={size}"
        # Test if the URL exists by making a HEAD request
        try:
            async with sess.head(icon_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    return icon_url
        except:
            continue
    
    # If no icon found, return placeholder
    return f"https://via.placeholder.com/{size}x{size}/cccccc/000000?text=No+Icon"


def save_failed_structures(failed_structures: Dict[str, Any]) -> None:
    """
    Save the failed structures cache to disk.

    Persists cache of structure IDs that failed to resolve, avoiding
    repeated attempts to fetch inaccessible citadel names.

    Args:
        failed_structures: Failed structures cache dictionary to save.
    """
    save_cache(FAILED_STRUCTURES_FILE, failed_structures)

def cleanup_contract_posts(allowed_corp_ids: set, allowed_issuer_ids: set) -> None:
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
    
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract", auth=get_wp_auth(), params={'per_page': WP_PER_PAGE})
    if response.status_code == 200:
        contracts = response.json()
        for contract in contracts:
            meta = contract.get('meta', {})
            status = meta.get('_eve_contract_status')
            issuer_corp_id = meta.get('_eve_contract_issuer_corp_id')
            issuer_id = meta.get('_eve_contract_issuer_id')
            contract_id = meta.get('_eve_contract_id')
            
            should_delete = False
            # Don't delete private contracts - they may still be visible to authorized characters
            # Only delete contracts from unauthorized issuers or finished/deleted contracts
            if status in ['finished', 'deleted']:
                should_delete = True
                logger.info(f"Deleting {status} contract: {contract_id}")
            elif issuer_corp_id and int(issuer_corp_id) not in allowed_corp_ids and issuer_id and int(issuer_id) not in allowed_issuer_ids:
                should_delete = True
                logger.info(f"Deleting contract from unauthorized issuer: {contract_id}")
            elif status == 'expired':
                # List expired contracts for manual deletion
                title = contract.get('title', {}).get('rendered', f'Contract {contract_id}')
                logger.info(f"EXPIRED CONTRACT TO DELETE MANUALLY: {title} (ID: {contract_id})")
            
            if should_delete:
                delete_wp_post('eve_contract', contract['id'])


def cleanup_blueprint_posts() -> None:
    """
    Clean up blueprint posts that don't match filtering criteria.

    Removes BPC posts (only tracks BPOs), blueprints from unauthorized corporations,
    and orphaned blueprint posts without proper ownership information.

    Note:
        Preserves blueprints from authenticated sources and allowed corporations.
        Currently hardcoded to only allow No Mercy Incorporated corporation blueprints.
    """
    logger.info("Cleaning up blueprint posts...")
    
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint", auth=get_wp_auth(), params={'per_page': WP_PER_PAGE})
    if response.status_code == 200:
        blueprints = response.json()
        for bp in blueprints:
            meta = bp.get('meta', {})
            quantity = meta.get('_eve_bp_quantity', -1)
            owner_id = meta.get('_eve_bp_owner_id')
            source = meta.get('_eve_bp_source', '')
            char_id = meta.get('_eve_char_id')
            
            # Remove BPCs (we only want to track BPOs now)
            if quantity != -1:
                bp_id = meta.get('_eve_bp_item_id')
                logger.info(f"Deleting BPC (quantity={quantity}): {bp_id}")
                delete_wp_post('eve_blueprint', bp['id'])
                continue
            
            # If it's from a corporation, check if it's No Mercy incorporated
            if owner_id and source.startswith('corp_'):
                # We need to check if this corp_id belongs to No Mercy incorporated
                corp_response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation?meta_key=_eve_corp_id&meta_value={owner_id}", auth=get_wp_auth())
                if corp_response.status_code == 200:
                    corp_posts = corp_response.json()
                    if not corp_posts:  # Corporation not found in our records
                        bp_id = bp.get('meta', {}).get('_eve_bp_item_id')
                        logger.info(f"Deleting blueprint from unknown corporation: {bp_id}")
                        delete_wp_post('eve_blueprint', bp['id'])
                    else:
                        corp_name = corp_posts[0].get('title', {}).get('rendered', '')
                        if corp_name.lower() != 'no mercy incorporated':
                            bp_id = bp.get('meta', {}).get('_eve_bp_item_id')
                            logger.info(f"Deleting blueprint from {corp_name}: {bp_id}")
                            delete_wp_post('eve_blueprint', bp['id'])
            # If it's from character assets/industry jobs and we don't have a char_id, it might be orphaned
            elif not char_id and not owner_id:
                # These are from the direct blueprint endpoints - check if they're corporation blueprints
                # For now, keep them as they come from authenticated sources
                pass


def cleanup_old_posts(allowed_corp_ids, allowed_issuer_ids):
    """
    Clean up posts that don't match filtering criteria.

    Orchestrates cleanup of both contract and blueprint posts to remove
    outdated or unauthorized content from the WordPress database.

    Args:
        allowed_corp_ids: Set of corporation IDs allowed for processing.
        allowed_issuer_ids: Set of character IDs allowed as issuers.

    Note:
        Called during full data fetches or contract-only processing to
        maintain clean, relevant content in WordPress.
    """
    logger.info("Starting cleanup of old posts...")
    
    cleanup_contract_posts(allowed_corp_ids, allowed_issuer_ids)
    cleanup_blueprint_posts()
    
    logger.info("Cleanup completed.")

if __name__ == "__main__":
    asyncio.run(main())