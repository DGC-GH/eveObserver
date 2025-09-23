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
from esi_oauth import save_tokens, load_tokens
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
        await cleanup_old_posts(allowed_corp_ids, allowed_issuer_ids)

        await process_all_data(corp_members, caches, args, tokens)

async def cleanup_old_posts(allowed_corp_ids, allowed_issuer_ids):
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
    
    await cleanup_contract_posts(allowed_corp_ids, allowed_issuer_ids)
    cleanup_blueprint_posts()
    
    logger.info("Cleanup completed.")

if __name__ == "__main__":
    asyncio.run(main())