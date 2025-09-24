#!/usr/bin/env python3
"""
Debug script for fetching and caching all outstanding contracts from The Forge region.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List

# Add the scripts directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

from api_client import fetch_public_contracts_async
from contract_processor import FORGE_REGION_ID

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def fetch_all_contracts_from_forge() -> List[Dict[str, Any]]:
    """Fetch all outstanding contracts from The Forge region without exceptions."""
    logger.info(f"Fetching all outstanding contracts from The Forge region (ID: {FORGE_REGION_ID})")

    all_contracts = []
    page = 1
    max_pages = 50  # Safety limit to prevent infinite loops

    while page <= max_pages:
        try:
            logger.info(f"Fetching page {page}...")
            contracts = await fetch_public_contracts_async(FORGE_REGION_ID, page=page)

            if not contracts:
                logger.info(f"No more contracts on page {page}, stopping")
                break

            logger.info(f"Found {len(contracts)} contracts on page {page}")

            # Process contracts and add to our list
            for contract in contracts:
                contract_id = contract.get("contract_id")
                if not contract_id:
                    logger.warning(f"Contract without ID found on page {page}, skipping")
                    continue

                # Create standardized contract data
                contract_data = {
                    "contract_id": contract_id,
                    "type": contract.get("type"),
                    "price": contract.get("price", 0),
                    "issuer_id": contract.get("issuer_id"),
                    "issuer_corporation_id": contract.get("issuer_corporation_id"),
                    "start_location_id": contract.get("start_location_id"),
                    "end_location_id": contract.get("end_location_id"),
                    "title": contract.get("title", ""),
                    "date_issued": contract.get("date_issued"),
                    "date_expired": contract.get("date_expired"),
                    "date_accepted": contract.get("date_accepted"),
                    "date_completed": contract.get("date_completed"),
                    "volume": contract.get("volume", 1),
                    "status": contract.get("status", "outstanding"),  # Public endpoint returns outstanding
                    "collateral": contract.get("collateral", 0),
                    "reward": contract.get("reward", 0),
                    "buyout": contract.get("buyout", 0),
                    "assignee_id": contract.get("assignee_id"),
                    "acceptor_id": contract.get("acceptor_id"),
                    "days_to_complete": contract.get("days_to_complete"),
                    "for_corporation": contract.get("for_corporation", False),
                }

                all_contracts.append(contract_data)
                logger.debug(f"Added contract {contract_id} of type {contract_data['type']}")

            page += 1

        except Exception as e:
            logger.error(f"Error fetching page {page}: {e}")
            # Continue to next page instead of stopping
            page += 1
            continue

    logger.info(f"Total contracts fetched: {len(all_contracts)}")
    return all_contracts


async def save_contracts_to_cache(contracts: List[Dict[str, Any]], cache_file: str) -> bool:
    """Save contracts to cache file."""
    try:
        # Ensure cache directory exists
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)

        # Save to file
        with open(cache_file, "w") as f:
            json.dump(contracts, f, indent=2, default=str)

        file_size = os.path.getsize(cache_file)
        logger.info(f"Saved {len(contracts)} contracts to {cache_file} ({file_size:,} bytes)")
        return True

    except Exception as e:
        logger.error(f"Error saving contracts to cache: {e}")
        return False


async def load_contracts_from_cache(cache_file: str) -> List[Dict[str, Any]]:
    """Load contracts from cache file."""
    try:
        if not os.path.exists(cache_file):
            logger.info(f"Cache file {cache_file} does not exist")
            return []

        with open(cache_file, "r") as f:
            contracts = json.load(f)

        logger.info(f"Loaded {len(contracts)} contracts from cache")
        return contracts

    except Exception as e:
        logger.error(f"Error loading contracts from cache: {e}")
        return []


async def analyze_contracts(contracts: List[Dict[str, Any]]):
    """Analyze the fetched contracts."""
    if not contracts:
        logger.warning("No contracts to analyze")
        return

    print(f"\n📊 CONTRACT ANALYSIS ({len(contracts)} total contracts)")
    print("=" * 60)

    # Contract types
    type_counts = {}
    status_counts = {}
    issuer_counts = {}
    corp_counts = {}

    for contract in contracts:
        # Type distribution
        ctype = contract.get("type", "unknown")
        type_counts[ctype] = type_counts.get(ctype, 0) + 1

        # Status distribution
        status = contract.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

        # Issuer analysis
        issuer_id = contract.get("issuer_id")
        if issuer_id:
            issuer_counts[issuer_id] = issuer_counts.get(issuer_id, 0) + 1

        corp_id = contract.get("issuer_corporation_id")
        if corp_id:
            corp_counts[corp_id] = corp_counts.get(corp_id, 0) + 1

    print("Contract Types:")
    for ctype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {ctype}: {count}")

    print(f"\nContract Status:")
    for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {status}: {count}")

    print(f"\nTop 10 Issuers by contract count:")
    for issuer_id, count in sorted(issuer_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  Issuer {issuer_id}: {count} contracts")

    print(f"\nTop 10 Corporations by contract count:")
    for corp_id, count in sorted(corp_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  Corp {corp_id}: {count} contracts")

    # Price analysis for item_exchange contracts
    item_exchange_prices = []
    for contract in contracts:
        if contract.get("type") == "item_exchange":
            price = contract.get("price", 0)
            if price > 0:
                item_exchange_prices.append(price)

    if item_exchange_prices:
        print(f"\nItem Exchange Price Analysis:")
        print(f"  Total item exchange contracts: {len(item_exchange_prices)}")
        print(f"  Average price: {sum(item_exchange_prices) / len(item_exchange_prices):,.2f} ISK")
        print(f"  Min price: {min(item_exchange_prices):,.2f} ISK")
        print(f"  Max price: {max(item_exchange_prices):,.2f} ISK")


async def main():
    """Main debug function."""
    print("🚀 Starting Forge contracts fetching and caching debug")
    print(f"Working directory: {os.getcwd()}")

    cache_file = os.path.join(os.path.dirname(__file__), "cache", "all_contracts_forge.json")

    # Check if cache exists and show current status
    if os.path.exists(cache_file):
        try:
            existing_contracts = await load_contracts_from_cache(cache_file)
            print(f"📁 Existing cache: {len(existing_contracts)} contracts")
        except:
            print("📁 Existing cache file exists but cannot be read")
    else:
        print("📁 No existing cache file")

    print("\n🔄 Fetching fresh contract data from The Forge...")

    # Fetch all contracts
    contracts = await fetch_all_contracts_from_forge()

    if contracts:
        print(f"✅ Successfully fetched {len(contracts)} contracts")

        # Analyze the data
        await analyze_contracts(contracts)

        # Save to cache
        print(f"\n💾 Saving to cache: {cache_file}")
        success = await save_contracts_to_cache(contracts, cache_file)

        if success:
            print("✅ Cache saved successfully")

            # Verify cache
            print("🔍 Verifying cache...")
            cached_contracts = await load_contracts_from_cache(cache_file)
            if len(cached_contracts) == len(contracts):
                print("✅ Cache verification successful")
            else:
                print(f"❌ Cache verification failed: expected {len(contracts)}, got {len(cached_contracts)}")
        else:
            print("❌ Failed to save cache")
    else:
        print("❌ No contracts fetched")

    print("\n🎉 Debug complete!")


if __name__ == "__main__":
    asyncio.run(main())
