"""
EVE Observer Contract Expansion
Handles expanding contract data with additional information and caching.
"""

import os
import json
import asyncio
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from api_client import fetch_public_esi, get_session, fetch_public_contract_items
from cache_manager_contracts import ContractCacheManager
from config import CACHE_DIR, ESI_BASE_URL

logger = logging.getLogger(__name__)


async def expand_single_contract_with_caching(
    contract: Dict[str, Any],
    issuer_cache: Dict[str, str],
    type_cache: Dict[str, Dict[str, Any]],
    corporation_cache: Dict[str, str],
    new_issuer_names: Dict[str, str],
    new_type_data: Dict[str, Dict[str, Any]],
    new_corporation_names: Dict[str, str],
    contract_items_cache: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """Expand a single contract, fetching missing data as needed."""
    contract_id = contract["contract_id"]
    contract_id_str = str(contract_id)
    logger.debug(f"Expanding contract {contract_id}")
    issuer_id = contract.get("issuer_id")
    issuer_corp_id = contract.get("issuer_corporation_id")

    # Create expanded contract
    expanded = contract.copy()

    # Get issuer name (fetch if missing)
    issuer_name = None
    if issuer_id:
        issuer_id_str = str(issuer_id)
        if issuer_id_str in issuer_cache:
            issuer_name = issuer_cache[issuer_id_str]
        elif issuer_id_str in new_issuer_names:
            issuer_name = new_issuer_names[issuer_id_str]
        else:
            # Need to fetch issuer name
            try:
                issuer_data = await fetch_public_esi(f"/characters/{issuer_id}/")
                if issuer_data and "name" in issuer_data:
                    issuer_name = issuer_data["name"]
                    new_issuer_names[issuer_id_str] = issuer_name
            except Exception as e:
                logger.warning(f"Failed to fetch issuer name for {issuer_id}: {e}")
                issuer_name = "Unknown"

    expanded["issuer_name"] = issuer_name or "Unknown"

    # Get corporation name (fetch if missing)
    corp_name = None
    if issuer_corp_id:
        corp_id_str = str(issuer_corp_id)
        if corp_id_str in corporation_cache:
            corp_name = corporation_cache[corp_id_str]
        elif corp_id_str in new_corporation_names:
            corp_name = new_corporation_names[corp_id_str]
        else:
            # Need to fetch corporation name
            try:
                corp_data = await fetch_public_esi(f"/corporations/{issuer_corp_id}/")
                if corp_data and "name" in corp_data:
                    corp_name = corp_data["name"]
                    new_corporation_names[corp_id_str] = corp_name
            except Exception as e:
                logger.warning(f"Failed to fetch corporation name for {issuer_corp_id}: {e}")
                corp_name = "Unknown"

    expanded["issuer_corporation_name"] = corp_name or "Unknown"

    # Handle contract items for item_exchange contracts
    if contract.get("type") == "item_exchange":
        # Check if items are already in the contract data (from cache)
        if "items" in contract and contract["items"]:
            # Items are already present, just ensure proper format
            items_details = []
            for item in contract["items"]:
                type_id = item.get("type_id")
                if type_id:
                    type_id_str = str(type_id)

                    # Get type data (fetch if missing)
                    type_data = None
                    if type_id_str in type_cache:
                        type_data = type_cache[type_id_str]
                    elif type_id_str in new_type_data:
                        type_data = new_type_data[type_id_str]
                    else:
                        # Need to fetch type data
                        try:
                            type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
                            if type_data:
                                new_type_data[type_id_str] = type_data
                        except Exception as e:
                            logger.warning(f"Failed to fetch type data for {type_id}: {e}")

                    # Build item details
                    item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"

                    item_detail = {
                        "type_id": type_id,
                        "name": item_name,
                        "quantity": item.get("quantity", 1),
                        "is_blueprint_copy": item.get("is_blueprint_copy", False)
                    }

                    # Determine blueprint type
                    if item_detail["is_blueprint_copy"]:
                        item_detail["blueprint_type"] = "BPC"
                        if "time_efficiency" in item and "material_efficiency" in item:
                            item_detail["time_efficiency"] = item.get("time_efficiency", 0)
                            item_detail["material_efficiency"] = item.get("material_efficiency", 0)
                    else:
                        group_id = type_data.get("group_id") if type_data else None
                        if group_id == 2:  # Blueprint group
                            item_detail["blueprint_type"] = "BPO"
                            item_detail["time_efficiency"] = None
                            item_detail["material_efficiency"] = None
                        else:
                            item_detail["blueprint_type"] = None

                    items_details.append(item_detail)

            expanded["items"] = items_details
            expanded["item_count"] = len(items_details)
        else:
            # No items data available - fetch from public API for public contracts
            try:
                logger.debug(f"Fetching items for contract {contract_id}")
                contract_items = await asyncio.to_thread(fetch_public_contract_items, contract_id)
                logger.debug(f"Fetched {len(contract_items) if contract_items else 0} items for contract {contract_id}")
                if contract_items:
                    # Store raw items in cache
                    contract_items_cache[contract_id_str] = contract_items

                    # Process the fetched items
                    items_details = []
                    for item in contract_items:
                        type_id = item.get("type_id")
                        if type_id:
                            type_id_str = str(type_id)

                            # Get type data (fetch if missing)
                            type_data = None
                            if type_id_str in type_cache:
                                type_data = type_cache[type_id_str]
                            elif type_id_str in new_type_data:
                                type_data = new_type_data[type_id_str]
                            else:
                                # Need to fetch type data
                                try:
                                    type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
                                    if type_data:
                                        new_type_data[type_id_str] = type_data
                                except Exception as e:
                                    logger.warning(f"Failed to fetch type data for {type_id}: {e}")

                            # Build item details
                            item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"

                            item_detail = {
                                "type_id": type_id,
                                "name": item_name,
                                "quantity": item.get("quantity", 1),
                                "is_blueprint_copy": item.get("is_blueprint_copy", False)
                            }

                            # Determine blueprint type
                            if item_detail["is_blueprint_copy"]:
                                item_detail["blueprint_type"] = "BPC"
                                if "time_efficiency" in item:
                                    item_detail["time_efficiency"] = item.get("time_efficiency", 0)
                                if "material_efficiency" in item:
                                    item_detail["material_efficiency"] = item.get("material_efficiency", 0)
                                if "runs" in item:
                                    item_detail["runs"] = item.get("runs", 1)
                            else:
                                group_id = type_data.get("group_id") if type_data else None
                                if group_id == 2:  # Blueprint group
                                    item_detail["blueprint_type"] = "BPO"
                                    item_detail["time_efficiency"] = None
                                    item_detail["material_efficiency"] = None
                                else:
                                    item_detail["blueprint_type"] = None

                            items_details.append(item_detail)

                    expanded["items"] = items_details
                    expanded["item_count"] = len(items_details)
                    logger.debug(f"Fetched {len(items_details)} items for contract {contract_id}")
                else:
                    # No items found
                    expanded["items"] = []
                    expanded["item_count"] = 0
            except Exception as e:
                logger.warning(f"Failed to fetch items for contract {contract_id}: {e}")
                expanded["items"] = []
                expanded["item_count"] = 0
    else:
        # Non-item_exchange contracts don't have items
        expanded["items"] = []
        expanded["item_count"] = 0

    return expanded


async def expand_new_contracts_dynamic(contracts: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """Expand new contracts with dynamic concurrency adjustment based on performance and rate limits.

    Args:
        contracts: List of new contracts to expand

    Returns:
        Tuple of (expanded_contracts, collected_items_cache)
    """
    if not contracts:
        return [], {}

    logger.info(f"Expanding {len(contracts)} new contracts with dynamic concurrency...")

    # Initialize cache manager
    cache_manager = ContractCacheManager(CACHE_DIR)

    # Load existing caches
    issuer_cache_task = asyncio.create_task(cache_manager.load_issuer_cache())
    type_cache_task = asyncio.create_task(cache_manager.load_type_cache())
    corporation_cache_task = asyncio.create_task(cache_manager.load_corporation_cache())

    issuer_cache, type_cache, corporation_cache = await asyncio.gather(
        issuer_cache_task, type_cache_task, corporation_cache_task
    )

    logger.info(f"Caches loaded - Issuer: {len(issuer_cache)}, Type: {len(type_cache)}, Corporation: {len(corporation_cache)}")

    # Dynamic parameters
    batch_size = 50  # Start smaller for new contracts
    semaphore_limit = 15  # Start with lower concurrency
    min_batch_size = 25
    max_batch_size = 200
    min_semaphore = 5
    max_semaphore = 50

    rate_limit_hits = 0
    max_rate_limit_hits = 3  # Reduce concurrency after this many rate limit errors

    expanded_contracts = []
    semaphore = asyncio.Semaphore(semaphore_limit)

    async def expand_contract_batch_dynamic(batch_contracts: List[Dict[str, Any]], batch_num: int) -> tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, List[Dict[str, Any]]], float, int]:
        """Expand a batch of contracts with error handling for rate limits."""
        batch_start_time = time.time()
        batch_expanded = []
        new_issuer_names: Dict[str, str] = {}
        new_type_data: Dict[str, Dict[str, Any]] = {}
        new_corporation_names: Dict[str, str] = {}
        new_contract_items: Dict[str, List[Dict[str, Any]]] = {}
        batch_rate_limit_hits = 0

        async def expand_single_contract_safe(contract: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with semaphore:
                try:
                    return await expand_single_contract_with_caching(
                        contract, issuer_cache, type_cache, corporation_cache,
                        new_issuer_names, new_type_data, new_corporation_names, new_contract_items
                    )
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'rate limit' in error_msg or '429' in error_msg:
                        nonlocal batch_rate_limit_hits
                        batch_rate_limit_hits += 1
                        logger.warning(f"Rate limit hit for contract {contract['contract_id']}, will retry later")
                        # Return None to indicate failure, will be retried
                        return None
                    else:
                        logger.error(f"Error expanding contract {contract['contract_id']}: {e}")
                        return None

        # Process contracts in this batch concurrently
        tasks = [expand_single_contract_safe(contract) for contract in batch_contracts]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in batch_results:
            if result and not isinstance(result, Exception):
                batch_expanded.append(result)

        batch_time = time.time() - batch_start_time
        return batch_expanded, new_issuer_names, new_type_data, new_corporation_names, new_contract_items, batch_time, batch_rate_limit_hits

    # Process in batches with dynamic adjustment
    remaining_contracts = contracts[:]
    batch_num = 1

    while remaining_contracts:
        current_batch = remaining_contracts[:batch_size]
        remaining_contracts = remaining_contracts[batch_size:]

        logger.debug(f"Processing batch {batch_num} with {len(current_batch)} contracts (batch_size={batch_size}, concurrency={semaphore_limit})")

        batch_expanded, new_issuers, new_types, new_corps, new_items, batch_time, batch_rate_limits = await expand_contract_batch_dynamic(current_batch, batch_num)

        # Handle rate limit hits
        if batch_rate_limits > 0:
            rate_limit_hits += batch_rate_limits
            logger.warning(f"Batch {batch_num} hit {batch_rate_limits} rate limits, total: {rate_limit_hits}")

            if rate_limit_hits >= max_rate_limit_hits:
                # Reduce concurrency significantly
                old_sem = semaphore_limit
                semaphore_limit = max(min_semaphore, semaphore_limit // 2)
                semaphore = asyncio.Semaphore(semaphore_limit)
                logger.warning(f"Too many rate limits, reducing concurrency: {old_sem} -> {semaphore_limit}")
                rate_limit_hits = 0  # Reset counter

        # Dynamic adjustment based on performance
        if batch_time > 20.0:  # Too slow
            old_batch = batch_size
            old_sem = semaphore_limit
            batch_size = max(min_batch_size, int(batch_size * 0.7))
            semaphore_limit = max(min_semaphore, int(semaphore_limit * 0.8))
            semaphore = asyncio.Semaphore(semaphore_limit)
            logger.debug(f"Batch {batch_num} slow ({batch_time:.1f}s), adjusting: batch_size {old_batch}->{batch_size}, concurrency {old_sem}->{semaphore_limit}")
        elif batch_time < 3.0 and rate_limit_hits == 0:  # Fast and no rate limits
            old_batch = batch_size
            old_sem = semaphore_limit
            batch_size = min(max_batch_size, int(batch_size * 1.3))
            semaphore_limit = min(max_semaphore, int(semaphore_limit * 1.2))
            semaphore = asyncio.Semaphore(semaphore_limit)
            logger.debug(f"Batch {batch_num} fast ({batch_time:.1f}s), adjusting: batch_size {old_batch}->{batch_size}, concurrency {old_sem}->{semaphore_limit}")

        # Accumulate results
        expanded_contracts.extend(batch_expanded)

        # Update caches incrementally
        issuer_cache.update(new_issuers)
        type_cache.update(new_types)
        corporation_cache.update(new_corps)

        batch_num += 1

        # Small delay between batches to be respectful
        await asyncio.sleep(0.1)

    # Save updated caches
    await cache_manager.save_issuer_cache(issuer_cache)
    await cache_manager.save_type_cache(type_cache)
    await cache_manager.save_corporation_cache(corporation_cache)

    logger.info(f"Successfully expanded {len(expanded_contracts)} new contracts")
    return expanded_contracts, {}  # collected_items_cache is empty since we update incrementally


async def expand_all_contracts_async(contracts: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """Expand all contracts asynchronously using on-demand data fetching and caching.

    This function implements an on-demand approach that:
    1. Loads existing caches (types, issuer names, corporation names)
    2. Expands contracts in parallel batches, fetching missing data as needed
    3. Caches new data for future use
    """
    logger.info(f"expand_all_contracts_async called with {len(contracts)} contracts")

    # Initialize cache manager
    cache_manager = ContractCacheManager(CACHE_DIR)

    # Load existing caches
    logger.info("Loading existing caches...")
    issuer_cache_task = asyncio.create_task(cache_manager.load_issuer_cache())
    type_cache_task = asyncio.create_task(cache_manager.load_type_cache())
    corporation_cache_task = asyncio.create_task(cache_manager.load_corporation_cache())

    issuer_cache, type_cache, corporation_cache = await asyncio.gather(
        issuer_cache_task, type_cache_task, corporation_cache_task
    )

    logger.info(f"Initial caches loaded - Issuer: {len(issuer_cache)}, Type: {len(type_cache)}, Corporation: {len(corporation_cache)}")

    # Process contracts in parallel batches with on-demand fetching and dynamic adjustment
    batch_size = 100  # Start with smaller batch size
    semaphore_limit = 20  # Start with lower concurrency
    min_batch_size = 50
    max_batch_size = 1000
    min_semaphore = 10
    max_semaphore = 200

    expanded_contracts = []
    semaphore = asyncio.Semaphore(semaphore_limit)  # Limit concurrent processing

    async def expand_contract_batch(batch_contracts: List[Dict[str, Any]], batch_num: int) -> tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, List[Dict[str, Any]]], float]:
        """Expand a batch of contracts, fetching missing data as needed."""
        batch_start_time = time.time()
        batch_expanded = []
        new_issuer_names: Dict[str, str] = {}
        new_type_data: Dict[str, Dict[str, Any]] = {}
        new_corporation_names: Dict[str, str] = {}
        new_contract_items: Dict[str, List[Dict[str, Any]]] = {}

        async def expand_single_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                return await expand_single_contract_with_caching(
                    contract, issuer_cache, type_cache, corporation_cache,
                    new_issuer_names, new_type_data, new_corporation_names, new_contract_items
                )

        # Process contracts in this batch concurrently
        tasks = [expand_single_contract(contract) for contract in batch_contracts]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in batch_results:
            if isinstance(result, Exception):
                logger.error(f"Error expanding contract: {result}")
                continue
            if result:
                batch_expanded.append(result)

        batch_time = time.time() - batch_start_time
        logger.info(f"Completed batch {batch_num}: {len(batch_expanded)} contracts expanded in {batch_time:.1f}s")
        return batch_expanded, new_issuer_names, new_type_data, new_corporation_names, new_contract_items, batch_time

    # Create tasks for parallel batch processing
    batch_tasks = []
    total_batches = (len(contracts) + batch_size - 1) // batch_size  # Ceiling division
    logger.info(f"Starting parallel processing of {total_batches} batches ({len(contracts)} contracts total) with initial batch_size={batch_size}, concurrency={semaphore_limit}")

    current_batch_size = batch_size
    current_semaphore_limit = semaphore_limit

    for batch_start in range(0, len(contracts), current_batch_size):
        batch_end = min(batch_start + current_batch_size, len(contracts))
        batch_contracts = contracts[batch_start:batch_end]
        batch_num = (batch_start // current_batch_size) + 1
        logger.info(f"Queueing batch {batch_num}: contracts {batch_start} to {batch_end-1} ({len(batch_contracts)} contracts)")
        batch_tasks.append(expand_contract_batch(batch_contracts, batch_num))

    # Wait for all batches to complete with progress updates
    logger.info("Processing batches concurrently...")
    start_time = time.time()
    completed_batches = 0

    # Initialize accumulation variables
    all_new_issuer_names = {}
    all_new_type_data = {}
    all_new_corporation_names = {}
    all_new_contract_items = {}

    for coro in asyncio.as_completed(batch_tasks):
        batch_result = await coro
        completed_batches += 1
        batch_expanded, new_issuers, new_types, new_corps, new_items, batch_time = batch_result

        # Dynamic adjustment based on performance
        if batch_time > 15.0:  # Too slow, reduce concurrency
            old_batch = current_batch_size
            old_sem = current_semaphore_limit
            current_batch_size = max(min_batch_size, int(current_batch_size * 0.8))
            current_semaphore_limit = max(min_semaphore, int(current_semaphore_limit * 0.9))
            if current_batch_size != old_batch or current_semaphore_limit != old_sem:
                logger.info(f"Batch {completed_batches} slow ({batch_time:.1f}s), adjusting: batch_size {old_batch}->{current_batch_size}, concurrency {old_sem}->{current_semaphore_limit}")
                semaphore = asyncio.Semaphore(current_semaphore_limit)  # Update semaphore
        elif batch_time < 5.0:  # Fast, can increase
            old_batch = current_batch_size
            old_sem = current_semaphore_limit
            current_batch_size = min(max_batch_size, int(current_batch_size * 1.2))
            current_semaphore_limit = min(max_semaphore, int(current_semaphore_limit * 1.1))
            if current_batch_size != old_batch or current_semaphore_limit != old_sem:
                logger.info(f"Batch {completed_batches} fast ({batch_time:.1f}s), adjusting: batch_size {old_batch}->{current_batch_size}, concurrency {old_sem}->{current_semaphore_limit}")
                semaphore = asyncio.Semaphore(current_semaphore_limit)  # Update semaphore

        # Log progress
        elapsed = time.time() - start_time
        progress_pct = (completed_batches / total_batches) * 100
        rate = completed_batches / elapsed if elapsed > 0 else 0
        eta = (total_batches - completed_batches) / rate if rate > 0 else 0
        logger.info(f"✓ Completed batch {completed_batches}/{total_batches} ({progress_pct:.1f}%): {len(batch_expanded)} contracts expanded in {batch_time:.1f}s, "
                   f"{len(new_issuers)} new issuers, {len(new_types)} new types, {len(new_corps)} new corps, "
                   f"{len(new_items)} new items. Elapsed: {elapsed:.1f}s")

        # Accumulate results
        expanded_contracts.extend(batch_expanded)
        all_new_issuer_names.update(new_issuers)
        all_new_type_data.update(new_types)
        all_new_corporation_names.update(new_corps)
        all_new_contract_items.update(new_items)

    logger.info(f"Expansion completed: {len(expanded_contracts)} contracts processed")

    # Update caches with new data
    if all_new_issuer_names:
        issuer_cache.update(all_new_issuer_names)
        await cache_manager.save_issuer_cache(issuer_cache)
        logger.info(f"Added {len(all_new_issuer_names)} new issuer names to cache")

    if all_new_type_data:
        type_cache.update(all_new_type_data)
        await cache_manager.save_type_cache(type_cache)
        logger.info(f"Added {len(all_new_type_data)} new type entries to cache")

    if all_new_corporation_names:
        corporation_cache.update(all_new_corporation_names)
        await cache_manager.save_corporation_cache(corporation_cache)
        logger.info(f"Added {len(all_new_corporation_names)} new corporation names to cache")

    logger.info(f"Asynchronously expanded {len(expanded_contracts)} contracts total")
    return expanded_contracts, all_new_contract_items


async def apply_cached_data_to_contracts(contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply cached expanded data to basic contracts to create fully expanded contracts.

    Loads all cached data (issuer names, corporation names, type data, contract items)
    and applies it to the basic contract data to create fully expanded contracts.
    """
    logger.info(f"Applying cached data to {len(contracts)} contracts...")

    # Initialize cache manager
    cache_manager = ContractCacheManager(CACHE_DIR)

    # Load all caches
    issuer_cache = await cache_manager.load_issuer_cache()
    corporation_cache = await cache_manager.load_corporation_cache()
    type_cache = await cache_manager.load_type_cache()
    contract_items_cache = await cache_manager.load_contract_items_cache()

    logger.info(f"Caches loaded - Issuer: {len(issuer_cache)}, Corporation: {len(corporation_cache)}, Type: {len(type_cache)}, Items: {len(contract_items_cache)}")

    expanded_contracts = []
    start_time = time.time()
    total_contracts = len(contracts)

    for i, contract in enumerate(contracts, 1):
        if i % 1000 == 0 or i == total_contracts:  # Log progress every 1000 contracts or at the end
            elapsed = time.time() - start_time
            progress_pct = (i / total_contracts) * 100
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total_contracts - i) / rate if rate > 0 else 0
            logger.info(f"Cache application progress: {i}/{total_contracts} contracts ({progress_pct:.1f}%) - "
                       f"Rate: {rate:.1f} contracts/sec, ETA: {eta:.1f}s")

        contract_id = contract["contract_id"]
        contract_id_str = str(contract_id)

        # Start with basic contract data
        expanded = contract.copy()

        # Apply issuer name from cache
        issuer_id = contract.get("issuer_id")
        if issuer_id:
            issuer_id_str = str(issuer_id)
            issuer_name = issuer_cache.get(issuer_id_str, "Unknown")
            expanded["issuer_name"] = issuer_name

        # Apply corporation name from cache
        issuer_corp_id = contract.get("issuer_corporation_id")
        if issuer_corp_id:
            corp_id_str = str(issuer_corp_id)
            corp_name = corporation_cache.get(corp_id_str, "Unknown")
            expanded["issuer_corporation_name"] = corp_name

        # Apply contract items from cache for item_exchange contracts
        if contract.get("type") == "item_exchange":
            cached_items = contract_items_cache.get(contract_id_str, [])
            if cached_items:
                items_details = []
                for item in cached_items:
                    type_id = item.get("type_id")
                    if type_id:
                        type_id_str = str(type_id)
                        type_data = type_cache.get(type_id_str, {})

                        # Build item details using cached type data
                        item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"

                        item_detail = {
                            "type_id": type_id,
                            "name": item_name,
                            "quantity": item.get("quantity", 1),
                            "is_blueprint_copy": item.get("is_blueprint_copy", False)
                        }

                        # Determine blueprint type
                        if item_detail["is_blueprint_copy"]:
                            item_detail["blueprint_type"] = "BPC"
                            item_detail["time_efficiency"] = item.get("time_efficiency", 0)
                            item_detail["material_efficiency"] = item.get("material_efficiency", 0)
                            item_detail["runs"] = item.get("runs", 1)
                        else:
                            group_id = type_data.get("group_id") if type_data else None
                            if group_id == 2:  # Blueprint group
                                item_detail["blueprint_type"] = "BPO"
                                item_detail["time_efficiency"] = None
                                item_detail["material_efficiency"] = None
                            else:
                                item_detail["blueprint_type"] = None

                        items_details.append(item_detail)

                expanded["items"] = items_details
                expanded["item_count"] = len(items_details)
            else:
                # No cached items available
                expanded["items"] = []
                expanded["item_count"] = 0
        else:
            # Non-item_exchange contracts don't have items
            expanded["items"] = []
            expanded["item_count"] = 0

        expanded_contracts.append(expanded)

    logger.info(f"Applied cached data to {len(expanded_contracts)} contracts")
    return expanded_contracts


async def fetch_and_expand_all_forge_contracts() -> List[Dict[str, Any]]:
    """Fetch and expand all contracts from The Forge region with incremental caching.

    Only processes new contracts, removes expired ones, and ensures cache reflects real-world EVE Online state.
    Returns blueprint-only contracts cache for competition analysis.
    """
    logger.info("Starting incremental contract processing for The Forge region...")

    # Load existing expanded contracts cache
    cache_file = os.path.join(CACHE_DIR, "all_contracts_forge.json")
    existing_expanded = []
    existing_contract_ids = set()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                existing_expanded = json.load(f)
                existing_contract_ids = {str(c["contract_id"]) for c in existing_expanded}
            logger.info(f"Loaded {len(existing_expanded)} existing expanded contracts from cache")
        except Exception as e:
            logger.warning(f"Failed to load existing cache: {e}")
            existing_expanded = []
            existing_contract_ids = set()

    # Fetch current contracts from API
    logger.info("Fetching current contracts from EVE Online API...")
    from contract_fetching import fetch_all_contracts_in_region
    current_contracts = await fetch_all_contracts_in_region(10000002)  # The Forge region
    current_contract_ids = {str(c["contract_id"]) for c in current_contracts}
    logger.info(f"Fetched {len(current_contracts)} current contracts from API")

    # Identify new contracts (in API but not in cache)
    new_contract_ids = current_contract_ids - existing_contract_ids
    new_contracts = [c for c in current_contracts if str(c["contract_id"]) in new_contract_ids]

    # Identify removed contracts (in cache but not in API - expired/fulfilled/deleted)
    removed_contract_ids = existing_contract_ids - current_contract_ids

    logger.info(f"Cache synchronization: {len(new_contract_ids)} new contracts, {len(removed_contract_ids)} removed contracts")

    # Remove expired contracts from cache
    if removed_contract_ids:
        existing_expanded = [c for c in existing_expanded if str(c["contract_id"]) not in removed_contract_ids]
        logger.info(f"Removed {len(removed_contract_ids)} expired contracts from cache")

    # Expand new contracts
    if new_contracts:
        logger.info(f"Expanding {len(new_contracts)} new contracts...")
        expanded_new, _ = await expand_new_contracts_dynamic(new_contracts)

        # Add to cache
        existing_expanded.extend(expanded_new)
        logger.info(f"Added {len(expanded_new)} expanded contracts to cache")
    else:
        logger.info("No new contracts to expand")

    # Save updated cache
    try:
        with open(cache_file, 'w') as f:
            json.dump(existing_expanded, f, indent=2, default=str)
        logger.info(f"Saved updated cache with {len(existing_expanded)} contracts")
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")
        raise

    # Build and return blueprint-only contracts cache for competition analysis
    blueprint_contracts = await build_blueprint_contracts_cache(existing_expanded)
    logger.info(f"Returning {len(blueprint_contracts)} blueprint contracts for competition analysis")
    return blueprint_contracts


async def build_blueprint_contracts_cache(all_expanded_contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build a cache containing only contracts with blueprints for competition analysis.

    This reduces memory usage by ~95% since only ~5% of contracts contain blueprints.

    Args:
        all_expanded_contracts: Full list of expanded contracts

    Returns:
        List of contracts that contain blueprints
    """
    logger.info(f"Building blueprint-only contracts cache from {len(all_expanded_contracts)} total contracts...")

    blueprint_contracts = []
    blueprint_count = 0

    for contract in all_expanded_contracts:
        if contract.get("type") == "item_exchange" and contract.get("items"):
            has_blueprint = False
            for item in contract["items"]:
                if item.get("blueprint_type") in ["BPO", "BPC"]:
                    has_blueprint = True
                    blueprint_count += 1
                    break

            if has_blueprint:
                blueprint_contracts.append(contract)

    logger.info(f"Blueprint contracts cache built: {len(blueprint_contracts)} contracts with {blueprint_count} blueprint items "
               f"({len(blueprint_contracts)/len(all_expanded_contracts)*100:.1f}% of total contracts)")

    return blueprint_contracts