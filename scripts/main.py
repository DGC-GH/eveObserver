#!/usr/bin/env python3
"""
EVE Observer Main Script
Orchestrates data fetching and processing for EVE Online data.
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

from api_client import get_session, refresh_token
from cache_manager import load_wp_post_id_cache
from config import LOG_FILE, LOG_LEVEL, TOKENS_FILE
from corporation_processor import process_corporation_data
from fetch_data import (
    clear_log_file,
    collect_corporation_members,
    get_allowed_entities,
    initialize_caches,
    process_character_data,
    cleanup_old_posts,
)

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def load_tokens() -> Dict[str, Any]:
    """Load stored tokens."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_tokens(tokens: Dict[str, Any]) -> None:
    """Save tokens to file."""
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
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


async def process_all_data(
    corp_members: Dict[int, List[Tuple[int, str, str]]],
    caches: Tuple[Dict[str, Any], ...],
    args: argparse.Namespace,
    tokens: Dict[str, Any],
) -> None:
    """Process all corporation and character data."""
    blueprint_cache, location_cache, structure_cache, failed_structures, wp_post_id_cache = caches

    # Process each corporation with any available member token
    processed_corps = set()
    for corp_id, members in corp_members.items():
        if corp_id in processed_corps:
            continue

        # Process data for the corporation and its members
        if args.all or args.corporations or args.blueprints:
            await process_corporation_data(
                corp_id,
                members,
                wp_post_id_cache,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures,
                args,
            )

        processed_corps.add(corp_id)

    # Now process individual character data (skills, blueprints, etc.)
    for char_id, token_data in tokens.items():
        if args.all or args.characters or args.skills or args.blueprints or args.planets or args.contracts:
            process_character_data(
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
    """Main data fetching routine."""
    start_time = time.time()
    args = parse_arguments()
    clear_log_file()
    caches = initialize_caches()
    tokens = load_tokens()
    if not tokens:
        logger.error("No authorized characters found. Run 'python esi_oauth.py authorize' first.")
        return

    try:
        # Collect all corporations and their member characters
        collect_start = time.time()
        corp_members = await collect_corporation_members(tokens)
        allowed_corp_ids, allowed_issuer_ids = get_allowed_entities(corp_members)
        collect_time = time.time() - collect_start
        logger.info(f"Corporation collection completed in {collect_time:.2f}s")

        # Clean up old posts with filtering (only if doing full fetch or contracts)
        if args.all or args.contracts:
            cleanup_start = time.time()
            await cleanup_old_posts(allowed_corp_ids, allowed_issuer_ids)
            cleanup_time = time.time() - cleanup_start
            logger.info(f"Post cleanup completed in {cleanup_time:.2f}s")

        process_start = time.time()
        await process_all_data(corp_members, caches, args, tokens)
        process_time = time.time() - process_start
        logger.info(f"Data processing completed in {process_time:.2f}s")

        total_time = time.time() - start_time
        logger.info(f"Total execution completed in {total_time:.2f}s")
    finally:
        # Flush any pending cache saves and log performance
        from cache_manager import flush_pending_saves, log_cache_performance

        flush_pending_saves()
        log_cache_performance()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
