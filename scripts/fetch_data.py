#!/usr/bin/env python3
"""
EVE Observer Data Fetcher
Fetches data from EVE ESI API and stores in WordPress database via REST API.
"""

import argparse
import asyncio
import json
import logging
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import requests
from dotenv import load_dotenv

from api_client import (
    delete_wp_post,
    fetch_esi,
    fetch_public_esi,
    fetch_type_icon,
    refresh_token,
    send_email,
    wp_request,
)
from blueprint_processor import (
    cleanup_blueprint_posts,
    extract_blueprints_from_assets,
    extract_blueprints_from_contracts,
    extract_blueprints_from_industry_jobs,
    update_blueprint_from_asset_in_wp,
    update_blueprint_in_wp,
)
from cache_manager import (
    get_cached_wp_post_id,
    load_blueprint_cache,
    load_failed_structures,
    load_location_cache,
    load_structure_cache,
    load_wp_post_id_cache,
    save_blueprint_cache,
    save_failed_structures,
    save_location_cache,
    save_structure_cache,
    save_wp_post_id_cache,
    set_cached_wp_post_id,
)
from character_processor import check_industry_job_completions, update_character_skills_in_wp, update_planet_in_wp
from config import *
from contract_processor import (
    cleanup_contract_posts,
    fetch_character_contracts,
    fetch_corporation_contracts,
    generate_contract_title,
    process_character_contracts,
    update_contract_in_wp,
)
from data_processors import fetch_character_data, get_wp_auth, update_character_in_wp
from esi_oauth import load_tokens, save_tokens
from utils import get_region_from_location


async def collect_corporation_members(tokens):
    corp_members = {}
    for char_id, token_data in tokens.items():
        try:
            expired = datetime.now(timezone.utc) > datetime.fromisoformat(
                token_data.get("expires_at", "2000-01-01T00:00:00+00:00")
            )
        except:
            expired = True
        if expired:
            new_token = refresh_token(token_data["refresh_token"])
            if new_token:
                token_data.update(new_token)
                save_tokens(tokens)
            else:
                logger.warning(f"Failed to refresh token for {token_data['name']}")
                continue

        access_token = token_data["access_token"]
        char_name = token_data["name"]

        # Fetch basic character data to get corporation
        char_data = await fetch_character_data(char_id, access_token)
        if char_data:
            await update_character_in_wp(char_id, char_data)
            corp_id = char_data.get("corporation_id")
            if corp_id:
                if corp_id not in corp_members:
                    corp_members[corp_id] = []
                corp_members[corp_id].append((char_id, access_token, char_name))

    return corp_members


async def process_character_data(
    char_id: int,
    token_data: Dict[str, Any],
    wp_post_id_cache: Dict[str, Any],
    blueprint_cache: Dict[str, Any],
    location_cache: Dict[str, Any],
    structure_cache: Dict[str, Any],
    failed_structures: Dict[str, Any],
    args: argparse.Namespace,
) -> None:
    """
    Process all data for a single character based on command line arguments.

    Fetches and processes character skills, blueprints, planets, and contracts
    according to the specified arguments.

    Args:
        char_id: EVE character ID to process.
        token_data: Token data dictionary for the character.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure cache.
        args: Parsed command line arguments.

    Note:
        Only processes data types specified in the arguments.
        Updates WordPress with fetched data.
    """
    access_token = token_data["access_token"]
    char_name = token_data["name"]

    logger.info(f"Processing character: {char_name} (ID: {char_id})")

    # Update character skills if requested
    if args.all or args.skills:
        await update_character_skills_in_wp(char_id, access_token)

    # Process blueprints if requested
    if args.all or args.blueprints:
        await process_character_blueprints(
            char_id, access_token, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures
        )

    # Process planets if requested
    if args.all or args.planets:
        await update_planet_in_wp(char_id, access_token)

    # Process contracts if requested
    if args.all or args.contracts:
        await process_character_contracts(
            char_id,
            access_token,
            char_name,
            wp_post_id_cache,
            blueprint_cache,
            location_cache,
            structure_cache,
            failed_structures,
        )


async def process_character_blueprints(
    char_id: int,
    access_token: str,
    wp_post_id_cache: Dict[str, Any],
    blueprint_cache: Dict[str, Any],
    location_cache: Dict[str, Any],
    structure_cache: Dict[str, Any],
    failed_structures: Dict[str, Any],
) -> None:
    """
    Process all blueprint data for a character.

    Fetches blueprints from direct ESI endpoint, assets, and industry jobs,
    then updates WordPress with the combined data.

    Args:
        char_id: EVE character ID.
        access_token: Valid OAuth2 access token.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure cache.
    """
    # Get blueprints from direct endpoint
    blueprints = await fetch_esi(f"/characters/{char_id}/blueprints", char_id, access_token)
    if blueprints:
        for bp in blueprints:
            await update_blueprint_in_wp(
                bp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures,
            )

    # Get blueprints from assets
    assets = await fetch_esi(f"/characters/{char_id}/assets", char_id, access_token)
    if assets:
        asset_blueprints = extract_blueprints_from_assets(assets, "char", char_id, access_token)
        for bp in asset_blueprints:
            await update_blueprint_from_asset_in_wp(
                bp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures,
            )

    # Get blueprints from industry jobs
    jobs = await fetch_esi(f"/characters/{char_id}/industry/jobs", char_id, access_token)
    if jobs:
        job_blueprints = extract_blueprints_from_industry_jobs(jobs, "char", char_id)
        for bp in job_blueprints:
            await update_blueprint_from_asset_in_wp(
                bp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures,
            )


# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)
# WordPress post ID cache
WP_POST_ID_CACHE_FILE = os.path.join(CACHE_DIR, "wp_post_ids.json")


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
    parser = argparse.ArgumentParser(description="Fetch EVE Online data from ESI API")
    parser.add_argument("--contracts", action="store_true", help="Fetch contracts data")
    parser.add_argument("--planets", action="store_true", help="Fetch planets data")
    parser.add_argument("--blueprints", action="store_true", help="Fetch blueprints data")
    parser.add_argument("--skills", action="store_true", help="Fetch skills data")
    parser.add_argument("--corporations", action="store_true", help="Fetch corporation data")
    parser.add_argument("--characters", action="store_true", help="Fetch character data")
    parser.add_argument("--all", action="store_true", help="Fetch all data (default)")

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
    with open(LOG_FILE, "w") as f:
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
        char_id
        for corp_id, members in corp_members.items()
        if corp_id == 98092220  # No Mercy Incorporated
        for char_id, access_token, char_name in members
    }
    return allowed_corp_ids, allowed_issuer_ids


async def process_all_data(
    corp_members: Dict[int, List[Tuple[int, str, str]]],
    caches: Tuple[Dict[str, Any], ...],
    args: argparse.Namespace,
    tokens: Dict[str, Any],
) -> None:
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
            await process_character_data(
                char_id,
                token_data,
                wp_post_id_cache,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures,
                args,
            )


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
