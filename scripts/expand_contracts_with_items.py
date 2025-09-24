#!/usr/bin/env python3
"""
Script to expand contract cache with item names and IDs using cached data.
Uses existing contract items cache and type data cache to populate contract items.
"""

import asyncio
import gzip
import json
import logging
import os
from typing import Any, Dict, List

from cache_manager_contracts import ContractCacheManager
from config import CACHE_DIR, LOG_FILE, LOG_LEVEL

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


async def load_contract_items_cache() -> Dict[str, List[Dict[str, Any]]]:
    """Load the contract items cache."""
    cache_file = os.path.join(CACHE_DIR, "contract_items_cache.json")
    if not os.path.exists(cache_file):
        logger.warning(f"Contract items cache file not found: {cache_file}")
        return {}

    try:
        with open(cache_file, "r") as f:
            data = json.load(f)
        logger.info(f"Loaded contract items cache with {len(data)} contracts")
        return data
    except Exception as e:
        logger.error(f"Failed to load contract items cache: {e}")
        return {}


async def expand_contracts_with_cached_items():
    """Expand contracts with item details using cached data."""
    logger.info("Starting contract expansion with cached item data...")

    # Load existing contract cache
    cache_file = os.path.join(CACHE_DIR, "all_contracts_forge.json")
    if not os.path.exists(cache_file):
        logger.error(f"Contract cache file not found: {cache_file}")
        return

    with open(cache_file, "r") as f:
        contracts = json.load(f)

    logger.info(f"Loaded {len(contracts)} contracts from cache")

    # Load contract items cache
    contract_items_cache = await load_contract_items_cache()
    if not contract_items_cache:
        logger.error("No contract items cache available")
        return

    # Initialize cache manager for type data
    cache_manager = ContractCacheManager(CACHE_DIR)

    # Load type data cache
    type_cache = await cache_manager.load_type_cache()
    logger.info(f"Loaded {len(type_cache)} type entries from cache")

    # Collect all type_ids that need to be fetched
    missing_type_ids = set()
    for contract_id_str, items in contract_items_cache.items():
        for item in items:
            type_id = item.get("type_id")
            if type_id and str(type_id) not in type_cache:
                missing_type_ids.add(type_id)

    logger.info(f"Found {len(missing_type_ids)} missing type IDs")

    # Fetch missing type data
    if missing_type_ids:
        logger.info("Fetching missing type data...")
        new_type_data = {}
        for type_id in missing_type_ids:
            try:
                from api_client import fetch_public_esi

                type_data = await fetch_public_esi(f"/universe/types/{type_id}")
                if type_data:
                    new_type_data[str(type_id)] = type_data
                    logger.debug(f"Fetched type data for {type_id}: {type_data.get('name', 'Unknown')}")
            except Exception as e:
                logger.warning(f"Failed to fetch type data for {type_id}: {e}")

        # Update type cache
        if new_type_data:
            type_cache.update(new_type_data)
            await cache_manager.save_type_cache(type_cache)
            logger.info(f"Added {len(new_type_data)} new type entries to cache")

    # Process contracts and expand with items
    expanded_count = 0
    contracts_with_items = 0

    for contract in contracts:
        contract_id = contract["contract_id"]
        contract_id_str = str(contract_id)

        # Check if this contract has items in the cache
        if contract_id_str in contract_items_cache:
            cached_items = contract_items_cache[contract_id_str]
            if cached_items:
                # Expand items with type data
                expanded_items = []
                for item in cached_items:
                    type_id = item.get("type_id")
                    if type_id:
                        type_id_str = str(type_id)

                        # Get type data
                        type_data = type_cache.get(type_id_str)
                        if type_data:
                            item_name = type_data.get("name", f"Type {type_id}")
                        else:
                            item_name = f"Type {type_id}"

                        # Build expanded item
                        expanded_item = {
                            "type_id": type_id,
                            "name": item_name,
                            "quantity": item.get("quantity", 1),
                            "is_blueprint_copy": item.get("is_blueprint_copy", False),
                        }

                        # Add blueprint-specific fields
                        if item.get("is_blueprint_copy"):
                            expanded_item["blueprint_type"] = "BPC"
                            if "time_efficiency" in item:
                                expanded_item["time_efficiency"] = item.get("time_efficiency")
                            if "material_efficiency" in item:
                                expanded_item["material_efficiency"] = item.get("material_efficiency")
                            if "runs" in item:
                                expanded_item["runs"] = item.get("runs")
                        else:
                            # Check if it's a BPO
                            group_id = type_data.get("group_id") if type_data else None
                            if group_id == 2:  # Blueprint group
                                expanded_item["blueprint_type"] = "BPO"
                            else:
                                expanded_item["blueprint_type"] = None

                        expanded_items.append(expanded_item)

                # Update contract with expanded items
                contract["items"] = expanded_items
                contract["item_count"] = len(expanded_items)
                contracts_with_items += 1

                logger.debug(f"Expanded contract {contract_id} with {len(expanded_items)} items")
            else:
                # Contract has empty items array
                contract["items"] = []
                contract["item_count"] = 0
        else:
            # Contract not in items cache
            contract["items"] = []
            contract["item_count"] = 0

        expanded_count += 1

    logger.info(f"Processed {expanded_count} contracts")
    logger.info(f"Expanded {contracts_with_items} contracts with item details")

    # Save the expanded contracts back to cache
    with open(cache_file, "w") as f:
        json.dump(contracts, f, indent=2, default=str)

    logger.info(f"Saved expanded contracts to {cache_file}")


async def main():
    """Main function."""
    logger.info("Starting contract expansion with cached data")

    await expand_contracts_with_cached_items()

    logger.info("Contract expansion completed")


if __name__ == "__main__":
    asyncio.run(main())
