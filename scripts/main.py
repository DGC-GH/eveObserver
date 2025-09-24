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

import psutil
from dotenv import load_dotenv

from api_client import get_session, refresh_token, cleanup_session
from cache_manager import load_wp_post_id_cache
from config import (
    CHARACTER_PROCESSING_CONCURRENCY,
    LOG_FILE,
    LOG_LEVEL,
    TOKENS_FILE,
    WORDPRESS_BATCH_SIZE,
)
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


def get_memory_usage() -> float:
    """Get current memory usage in MB."""
    try:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # Convert to MB
    except ImportError:
        return 0.0  # psutil not available


async def log_performance_metrics(
    total_time: float,
    api_calls: int,
    contracts_processed: int,
    characters_processed: int,
    cache_stats: Dict[str, Any]
) -> None:
    """Log detailed performance metrics for monitoring."""
    memory_mb = get_memory_usage()

    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "execution_time_seconds": round(total_time, 2),
        "api_calls": api_calls,
        "memory_usage_mb": round(memory_mb, 2),
        "contracts_processed": contracts_processed,
        "characters_processed": characters_processed,
        "cache_hit_rate": cache_stats.get("hit_rate", 0),
        "cache_hits": cache_stats.get("hits", 0),
        "cache_misses": cache_stats.get("misses", 0),
        "character_concurrency": CHARACTER_PROCESSING_CONCURRENCY,
        "wordpress_batch_size": WORDPRESS_BATCH_SIZE,
    }

    # Log to console and save to file
    logger.info(f"PERFORMANCE METRICS: {json.dumps(metrics, indent=2)}")

    # Save to performance log file
    perf_log_file = os.path.join(os.path.dirname(LOG_FILE), "performance_metrics.jsonl")
    try:
        with open(perf_log_file, "a") as f:
            f.write(json.dumps(metrics) + "\n")
    except Exception as e:
        logger.warning(f"Failed to save performance metrics: {e}")


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

    # Now process individual character data in parallel (skills, blueprints, etc.)
    if args.all or args.characters or args.skills or args.blueprints or args.planets or args.contracts:
        logger.info("Processing character data in parallel...")
        character_tasks = []
        for char_id, token_data in tokens.items():
            char_id = int(char_id)  # Ensure char_id is an integer
            task = process_character_data(
                char_id,
                token_data,
                wp_post_id_cache,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures,
                args,
            )
            character_tasks.append(task)

        # Execute character processing in parallel with concurrency control
        semaphore = asyncio.Semaphore(CHARACTER_PROCESSING_CONCURRENCY)  # Configurable concurrency limit
        async def process_with_semaphore(task):
            async with semaphore:
                return await task

        character_start = time.time()
        await asyncio.gather(*[process_with_semaphore(task) for task in character_tasks])
        character_time = time.time() - character_start
        logger.info(f"Parallel character processing completed in {character_time:.2f}s for {len(character_tasks)} characters")


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
        
        # Log performance metrics
        cache_stats = {}  # Will be populated by log_cache_performance
        await log_performance_metrics(
            total_time=total_time,
            api_calls=0,  # TODO: Track API calls
            contracts_processed=0,  # TODO: Track contracts processed
            characters_processed=len(tokens),
            cache_stats=cache_stats
        )
        
        # Cleanup session
        await cleanup_session()
    finally:
        # Flush any pending cache saves and log performance
        from cache_manager import flush_pending_saves, log_cache_performance

        flush_pending_saves()
        log_cache_performance()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
