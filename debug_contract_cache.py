#!/usr/bin/env python3
"""
Debug script for all_contracts_forge.json cache creation.
This script traces through the contract processing pipeline step by step.
"""

import asyncio
import json
import logging
import sys
import os

# Add the scripts directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from contract_processor import (
    fetch_and_expand_all_forge_contracts,
    fetch_all_contracts_in_region,
    expand_all_contracts,
    FORGE_REGION_ID
)
from config import CACHE_DIR

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def debug_contract_cache_creation():
    """Debug the creation of all_contracts_forge.json cache."""
    logger.info("=== Starting debug of all_contracts_forge.json cache creation ===")

    cache_file = os.path.join(CACHE_DIR, "all_contracts_forge.json")
    logger.info(f"Cache file location: {cache_file}")

    # Step 1: Fetch basic contracts from The Forge region
    logger.info("\n=== Step 1: Fetching basic contracts from The Forge region ===")
    logger.info(f"Region ID: {FORGE_REGION_ID}")

    try:
        basic_contracts = await fetch_all_contracts_in_region(FORGE_REGION_ID)
        logger.info(f"✓ Fetched {len(basic_contracts) if basic_contracts else 0} basic contracts")

        if basic_contracts:
            # Show sample of basic contract data
            logger.info("Sample basic contract data:")
            for i, contract in enumerate(basic_contracts[:3]):
                logger.info(f"  Contract {i+1}: ID={contract.get('contract_id')}, "
                           f"type={contract.get('type')}, "
                           f"price={contract.get('price')}, "
                           f"issuer_id={contract.get('issuer_id')}")

            # Count contract types
            contract_types = {}
            for contract in basic_contracts:
                ctype = contract.get('type', 'unknown')
                contract_types[ctype] = contract_types.get(ctype, 0) + 1

            logger.info(f"Contract type breakdown: {contract_types}")

        else:
            logger.error("✗ Failed to fetch basic contracts")
            return

    except Exception as e:
        logger.error(f"✗ Error fetching basic contracts: {e}")
        return

    # Step 2: Expand contracts with full details
    logger.info("\n=== Step 2: Expanding contracts with full details ===")

    try:
        expanded_contracts = await expand_all_contracts(basic_contracts)
        logger.info(f"✓ Expanded to {len(expanded_contracts) if expanded_contracts else 0} contracts with full details")

        if expanded_contracts:
            # Show sample of expanded contract data
            logger.info("Sample expanded contract data:")
            for i, contract in enumerate(expanded_contracts[:2]):
                items = contract.get('items', [])
                logger.info(f"  Contract {i+1}: ID={contract.get('contract_id')}, "
                           f"issuer='{contract.get('issuer_name')}', "
                           f"corp='{contract.get('issuer_corporation_name')}', "
                           f"items={len(items)}")

                # Show item details for first contract
                if i == 0 and items:
                    for j, item in enumerate(items[:2]):
                        logger.info(f"    Item {j+1}: {item.get('name')} (x{item.get('quantity')}, "
                                   f"type={item.get('blueprint_type')})")

    except Exception as e:
        logger.error(f"✗ Error expanding contracts: {e}")
        return

    # Step 3: Save to cache file
    logger.info("\n=== Step 3: Saving to cache file ===")

    try:
        with open(cache_file, 'w') as f:
            json.dump(expanded_contracts, f, indent=2, default=str)

        # Check file size
        file_size = os.path.getsize(cache_file)
        logger.info(f"✓ Saved cache file: {cache_file}")
        logger.info(f"✓ File size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")

        # Verify the cache was saved correctly
        with open(cache_file, 'r') as f:
            saved_data = json.load(f)

        logger.info(f"✓ Verification: {len(saved_data)} contracts in saved cache")

        # Show final statistics
        item_exchange_count = sum(1 for c in saved_data if c.get('type') == 'item_exchange')
        logger.info(f"✓ Final stats: {len(saved_data)} total contracts, "
                   f"{item_exchange_count} item exchange contracts")

    except Exception as e:
        logger.error(f"✗ Error saving cache: {e}")
        return

    logger.info("\n=== Debug completed successfully! ===")

async def main():
    """Main entry point."""
    await debug_contract_cache_creation()

if __name__ == "__main__":
    asyncio.run(main())