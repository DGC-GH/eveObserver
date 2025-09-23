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
    extract_blueprints_from_contracts, update_blueprint_from_asset_in_wp, cleanup_blueprint_posts
)
from character_processor import update_character_skills_in_wp, check_industry_job_completions, update_planet_in_wp
from contract_processor import (
    fetch_character_contracts, fetch_corporation_contracts, process_character_contracts, cleanup_contract_posts,
    generate_contract_title, update_contract_in_wp
)
from data_processors import fetch_character_data, update_character_in_wp, get_wp_auth
from cache_manager import (
    load_blueprint_cache, save_blueprint_cache, load_location_cache, save_location_cache,
    load_structure_cache, save_structure_cache, load_failed_structures, save_failed_structures,
    load_wp_post_id_cache, save_wp_post_id_cache, get_cached_wp_post_id, set_cached_wp_post_id
)
from api_client import fetch_public_esi, fetch_esi, wp_request, send_email, refresh_token, fetch_type_icon, delete_wp_post
from utils import get_region_from_location
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
    Process all character data based on command line arguments.

    Orchestrates the fetching and processing of data for all authorized characters,
    respecting the selected data types.

    Args:
        corp_members: Corporation members grouped by corporation ID (for reference).
        caches: Tuple of cache dictionaries.
        args: Parsed command line arguments.
        tokens: Dictionary of token data keyed by character ID.

    Note:
        Processes individual character data including skills, blueprints, planets, and contracts.
        Corporation data is now handled separately in corporation_processor.py.
    """
    blueprint_cache, location_cache, structure_cache, failed_structures, wp_post_id_cache = caches
    
    # Process individual character data (skills, blueprints, planets, contracts)
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