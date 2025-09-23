#!/usr/bin/env python3
"""
EVE Observer Main Script
Orchestrates data fetching and processing for EVE Online data.
"""

import os
import json
import logging
from typing import Dict, List, Tuple
from datetime import datetime, timezone
from dotenv import load_dotenv

from config import *
from api_client import refresh_token, get_session
from cache_manager import load_wp_post_id_cache
from data_processors import (
    collect_corporation_members, process_corporation_data, process_character_data,
    cleanup_old_posts, clear_log_file, initialize_caches, get_allowed_entities
)

load_dotenv()

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

def load_tokens() -> Dict[str, Any]:
    """Load stored tokens."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_tokens(tokens: Dict[str, Any]) -> None:
    """Save tokens to file."""
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f)

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
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

def process_all_data(corp_members: Dict[int, List[Tuple[int, str, str]]], caches: Tuple[Dict[str, Any], ...], args: argparse.Namespace, tokens: Dict[str, Any]) -> None:
    """Process all corporation and character data."""
    blueprint_cache, location_cache, structure_cache, failed_structures, wp_post_id_cache = caches
    
    # Process each corporation with any available member token
    processed_corps = set()
    for corp_id, members in corp_members.items():
        if corp_id in processed_corps:
            continue

        # Process data for the corporation and its members
        if args.all or args.corporations or args.blueprints:
            process_corporation_data(corp_id, members, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures, args)

        processed_corps.add(corp_id)

    # Now process individual character data (skills, blueprints, etc.)
    for char_id, token_data in tokens.items():
        if args.all or args.characters or args.skills or args.blueprints or args.planets or args.contracts:
            process_character_data(char_id, token_data, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures, args)

def main() -> None:
    """Main data fetching routine."""
    args = parse_arguments()
    clear_log_file()
    caches = initialize_caches()
    tokens = load_tokens()
    if not tokens:
        logger.error("No authorized characters found. Run 'python esi_oauth.py authorize' first.")
        return

    try:
        # Collect all corporations and their member characters
        corp_members = collect_corporation_members(tokens)
        allowed_corp_ids, allowed_issuer_ids = get_allowed_entities(corp_members)

        # Clean up old posts with filtering (only if doing full fetch or contracts)
        if args.all or args.contracts:
            cleanup_old_posts(allowed_corp_ids, allowed_issuer_ids)

        process_all_data(corp_members, caches, args, tokens)
    finally:
        # Flush any pending cache saves and log performance
        from cache_manager import flush_pending_saves, log_cache_performance
        flush_pending_saves()
        log_cache_performance()

if __name__ == "__main__":
    import argparse
    main()