#!/usr/bin/env python3
"""
Script to extract contract items from all_contracts_forge.json and save to contract_items_cache.json
"""

import json
import os
import logging

from config import CACHE_DIR, LOG_FILE, LOG_LEVEL

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def extract_items_to_cache():
    """Extract contract items from all_contracts_forge.json and save to contract_items_cache.json"""
    logger.info("Starting extraction of contract items to cache...")

    # Load contracts from all_contracts_forge.json
    contracts_file = os.path.join(CACHE_DIR, "all_contracts_forge.json")
    if not os.path.exists(contracts_file):
        logger.error(f"Contracts file not found: {contracts_file}")
        return

    with open(contracts_file, 'r') as f:
        contracts = json.load(f)

    logger.info(f"Loaded {len(contracts)} contracts from {contracts_file}")

    # Extract items for each contract
    contract_items_cache = {}
    contracts_with_items = 0
    total_items = 0

    for contract in contracts:
        contract_id = contract.get("contract_id")
        if not contract_id:
            continue

        contract_id_str = str(contract_id)
        items = contract.get("items", [])

        # Convert expanded items back to raw format for cache
        raw_items = []
        for item in items:
            raw_item = {
                "type_id": item.get("type_id"),
                "quantity": item.get("quantity", 1),
                "is_blueprint_copy": item.get("is_blueprint_copy", False)
            }

            # Add blueprint-specific fields if present
            if item.get("is_blueprint_copy"):
                if "time_efficiency" in item:
                    raw_item["time_efficiency"] = item.get("time_efficiency")
                if "material_efficiency" in item:
                    raw_item["material_efficiency"] = item.get("material_efficiency")
                if "runs" in item:
                    raw_item["runs"] = item.get("runs")

            raw_items.append(raw_item)

        contract_items_cache[contract_id_str] = raw_items

        if raw_items:
            contracts_with_items += 1
            total_items += len(raw_items)

    logger.info(f"Extracted items for {contracts_with_items} contracts with {total_items} total items")

    # Save to contract_items_cache.json
    cache_file = os.path.join(CACHE_DIR, "contract_items_cache.json")
    with open(cache_file, 'w') as f:
        json.dump(contract_items_cache, f, indent=2)

    logger.info(f"Saved contract items cache to {cache_file}")


if __name__ == "__main__":
    extract_items_to_cache()