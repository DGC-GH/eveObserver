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

from api_client import api_call_counter, cleanup_session, get_session, refresh_token
from cache_manager import load_wp_post_id_cache
from config import CHARACTER_PROCESSING_CONCURRENCY, LOG_FILE, LOG_LEVEL, TOKENS_FILE, WORDPRESS_BATCH_SIZE
from corporation_processor import process_corporation_data
from fetch_data import (
    cleanup_old_posts,
    clear_log_file,
    collect_corporation_members,
    get_allowed_entities,
    initialize_caches,
    process_character_data,
)
from utils import parse_arguments

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

PID_FILE = os.path.join(os.path.dirname(__file__), "main.pid")
STATUS_FILE = os.path.join(os.path.dirname(__file__), "sync_status.json")


def check_single_instance() -> bool:
    """Check if another instance is running and prevent multiple executions."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            
            # Check if process is still running
            if psutil.pid_exists(old_pid):
                logger.warning(f"Another instance is already running (PID: {old_pid}). Exiting.")
                return False
            else:
                logger.info(f"Removing stale PID file for dead process {old_pid}")
                os.remove(PID_FILE)
        except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
            logger.info("Removing invalid PID file")
            os.remove(PID_FILE)
    
    # Create new PID file
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
        logger.info(f"Created PID file: {PID_FILE}")
    except Exception as e:
        logger.error(f"Failed to create PID file: {e}")
        return False
    
    return True


def cleanup_pid_file():
    """Remove the PID file on exit."""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            logger.info("Removed PID file")
    except Exception as e:
        logger.warning(f"Failed to remove PID file: {e}")


def update_sync_status(status: str, progress: float = 0.0, message: str = "", section: str = "", stages: Dict[str, Dict[str, Any]] = None):
    """Update the sync status file with current progress."""
    try:
        status_data = {
            "pid": os.getpid(),
            "status": status,
            "progress": progress,
            "message": message,
            "section": section,
            "stages": stages or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "start_time": getattr(update_sync_status, 'start_time', datetime.now(timezone.utc).isoformat())
        }
        
        # Store start time for the first call
        if not hasattr(update_sync_status, 'start_time'):
            update_sync_status.start_time = status_data["start_time"]
        
        with open(STATUS_FILE, 'w') as f:
            json.dump(status_data, f, indent=2)
        
        logger.info(f"Sync status updated: {status} - {progress:.1f}% - {message}")
    except Exception as e:
        logger.error(f"Failed to update sync status: {e}")


def cleanup_status_file():
    """Remove the status file on exit."""
    try:
        if os.path.exists(STATUS_FILE):
            os.remove(STATUS_FILE)
            logger.info("Removed status file")
    except Exception as e:
        logger.warning(f"Failed to remove status file: {e}")


def check_sync_running() -> Dict[str, Any]:
    """Check if a sync is currently running and return status."""
    if not os.path.exists(STATUS_FILE):
        return {"running": False}
    
    try:
        with open(STATUS_FILE, 'r') as f:
            status_data = json.load(f)
        
        # Check if the process is still running
        pid = status_data.get("pid")
        if pid and psutil.pid_exists(pid):
            return {
                "running": True,
                "status": status_data.get("status", "unknown"),
                "progress": status_data.get("progress", 0.0),
                "message": status_data.get("message", ""),
                "section": status_data.get("section", ""),
                "stages": status_data.get("stages", {}),
                "timestamp": status_data.get("timestamp", ""),
                "start_time": status_data.get("start_time", ""),
                "pid": pid
            }
        else:
            # Process is dead, clean up
            cleanup_status_file()
            return {"running": False}
    except Exception as e:
        logger.error(f"Error checking sync status: {e}")
        return {"running": False}


def get_memory_usage() -> float:
    """Get current memory usage in MB."""
    try:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # Convert to MB
    except ImportError:
        return 0.0  # psutil not available


async def log_performance_metrics(
    total_time: float, api_calls: int, contracts_processed: int, characters_processed: int, cache_stats: Dict[str, Any]
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


async def process_all_data(
    corp_members: Dict[int, List[Tuple[int, str, str]]],
    caches: Tuple[Dict[str, Any], ...],
    args: argparse.Namespace,
    tokens: Dict[str, Any],
) -> None:
    """Process all corporation and character data."""
    blueprint_cache, location_cache, structure_cache, failed_structures, wp_post_id_cache = caches

    # Fetch all expanded contracts once for competition analysis if processing contracts
    all_expanded_contracts = None
    if args.all or args.contracts:
        from contract_expansion import fetch_and_expand_all_forge_contracts
        try:
            all_expanded_contracts = await fetch_and_expand_all_forge_contracts()
            logger.info(f"Fetched {len(all_expanded_contracts) if all_expanded_contracts else 0} expanded contracts for competition analysis")
        except Exception as e:
            logger.error(f"Failed to fetch expanded contracts: {e}")
            all_expanded_contracts = None

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
                all_expanded_contracts,
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
                all_expanded_contracts,
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
async def main() -> None:
    """Main data fetching routine."""
    if not check_single_instance():
        return

    try:
        # Initialize sync status with stages
        stages = {
            "initialization": {"progress": 0, "status": "pending", "message": "Preparing..."},
            "collection": {"progress": 0, "status": "pending", "message": "Preparing..."},
            "processing": {"progress": 0, "status": "pending", "message": "Preparing..."},
            "finalization": {"progress": 0, "status": "pending", "message": "Preparing..."}
        }
        update_sync_status("starting", 0.0, "Initializing sync process...", "", stages)
        
        start_time = time.time()
        args = parse_arguments()
        clear_log_file()
        
        # Update initialization stage
        stages["initialization"]["status"] = "running"
        stages["initialization"]["progress"] = 25
        stages["initialization"]["message"] = "Loading caches and tokens..."
        update_sync_status("initializing", 5.0, "Loading caches and tokens...", "", stages)
        
        caches = initialize_caches()
        tokens = load_tokens()
        if not tokens:
            logger.error("No authorized characters found. Run 'python esi_oauth.py authorize' first.")
            stages["initialization"]["status"] = "error"
            stages["initialization"]["message"] = "No authorized characters found"
            update_sync_status("error", 0.0, "No authorized characters found", "", stages)
            cleanup_pid_file()
            cleanup_status_file()
            return

        # Complete initialization stage
        stages["initialization"]["status"] = "completed"
        stages["initialization"]["progress"] = 100
        stages["initialization"]["message"] = "Initialization completed"
        
        # Start collection stage
        stages["collection"]["status"] = "running"
        stages["collection"]["progress"] = 10
        stages["collection"]["message"] = "Collecting corporation members..."
        update_sync_status("collecting", 10.0, "Collecting corporation members...", "", stages)
        
        collect_start = time.time()
        corp_members = await collect_corporation_members(tokens)
        allowed_corp_ids, allowed_issuer_ids = get_allowed_entities(corp_members)
        collect_time = time.time() - collect_start
        logger.info(f"Corporation collection completed in {collect_time:.2f}s")
        
        stages["collection"]["progress"] = 50
        stages["collection"]["message"] = f"Found {len(corp_members)} corporations with {sum(len(members) for members in corp_members.values())} total members"
        update_sync_status("collecting", 20.0, f"Found {len(corp_members)} corporations with {sum(len(members) for members in corp_members.values())} total members", "", stages)

        # Clean up old posts with filtering (only if doing full fetch or contracts)
        if args.all or args.contracts:
            stages["collection"]["progress"] = 75
            stages["collection"]["message"] = "Cleaning up old posts..."
            update_sync_status("cleaning", 25.0, "Cleaning up old posts...", "", stages)
            
            cleanup_start = time.time()
            await cleanup_old_posts(allowed_corp_ids, allowed_issuer_ids)
            cleanup_time = time.time() - cleanup_start
            logger.info(f"Post cleanup completed in {cleanup_time:.2f}s")
            
            stages["collection"]["progress"] = 100
            stages["collection"]["message"] = f"Post cleanup completed in {cleanup_time:.2f}s"
            update_sync_status("cleaning", 30.0, f"Post cleanup completed in {cleanup_time:.2f}s", "", stages)

        # Complete collection stage
        stages["collection"]["status"] = "completed"
        
        # Start processing stage
        stages["processing"]["status"] = "running"
        stages["processing"]["progress"] = 10
        stages["processing"]["message"] = "Processing corporation and character data..."
        update_sync_status("processing", 35.0, "Processing corporation and character data...", "", stages)
        
        process_start = time.time()
        await process_all_data(corp_members, caches, args, tokens)
        process_time = time.time() - process_start
        logger.info(f"Data processing completed in {process_time:.2f}s")
        
        stages["processing"]["progress"] = 90
        stages["processing"]["message"] = f"Data processing completed in {process_time:.2f}s"
        update_sync_status("processing", 90.0, f"Data processing completed in {process_time:.2f}s", "", stages)

        total_time = time.time() - start_time
        
        # Complete processing stage
        stages["processing"]["status"] = "completed"
        stages["processing"]["progress"] = 100
        
        # Start finalization stage
        stages["finalization"]["status"] = "running"
        stages["finalization"]["progress"] = 25
        stages["finalization"]["message"] = "Finalizing and logging performance metrics..."
        update_sync_status("finalizing", 95.0, "Finalizing and logging performance metrics...", "", stages)

        # Log performance metrics
        cache_stats = {}  # Will be populated by log_cache_performance
        await log_performance_metrics(
            total_time=total_time,
            api_calls=api_call_counter.get(),  # Track API calls
            contracts_processed=0,  # TODO: Track contracts processed
            characters_processed=len(tokens),
            cache_stats=cache_stats,
        )

        # Cleanup session
        await cleanup_session()
        
        stages["finalization"]["progress"] = 100
        stages["finalization"]["message"] = f"Sync completed successfully in {total_time:.2f}s"
        stages["finalization"]["status"] = "completed"
        
        update_sync_status("completed", 100.0, f"Sync completed successfully in {total_time:.2f}s", "", stages)
        logger.info("Sync completed successfully")
        
    except Exception as e:
        error_msg = f"Sync failed: {str(e)}"
        logger.error(error_msg)
        
        # Mark current stage as failed
        for stage_name, stage_data in stages.items():
            if stage_data["status"] == "running":
                stage_data["status"] = "error"
                stage_data["message"] = str(e)
                break
        
        update_sync_status("error", 0.0, error_msg, "", stages)
        raise
    finally:
        # Flush any pending cache saves and log performance
        from cache_manager import flush_pending_saves, log_cache_performance

        flush_pending_saves()
        log_cache_performance()
        cleanup_pid_file()
        # Don't cleanup status file immediately - let it persist for a bit so dashboard can show final status


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
