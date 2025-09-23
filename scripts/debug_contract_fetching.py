#!/usr/bin/env python3
"""
Debug script for testing contract fetching, storing, and expanding functionality.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, List, Any

# Add the scripts directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

from contract_processor import (
    fetch_and_expand_all_forge_contracts,
    fetch_all_contracts_in_region,
    expand_all_contracts,
    FORGE_REGION_ID
)
from api_client import fetch_public_contracts_async, fetch_public_contract_items_async

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def debug_fetch_all_contracts_in_region():
    """Debug the fetch_all_contracts_in_region function."""
    print("=" * 80)
    print("DEBUGGING: fetch_all_contracts_in_region")
    print("=" * 80)

    try:
        print(f"Fetching contracts from region {FORGE_REGION_ID}...")
        contracts = await fetch_all_contracts_in_region(FORGE_REGION_ID)

        print(f"✅ Successfully fetched {len(contracts)} contracts")

        # Show sample contracts
        print("\n📋 Sample contracts (first 3):")
        for i, contract in enumerate(contracts[:3]):
            print(f"  Contract {i+1}:")
            print(f"    ID: {contract.get('contract_id')}")
            print(f"    Type: {contract.get('type')}")
            print(f"    Price: {contract.get('price', 0):,.2f} ISK")
            print(f"    Issuer ID: {contract.get('issuer_id')}")
            print(f"    Corp ID: {contract.get('issuer_corporation_id')}")
            print(f"    Status: {contract.get('status')}")
            print()

        # Analyze contract types
        contract_types = {}
        for contract in contracts:
            ctype = contract.get('type', 'unknown')
            contract_types[ctype] = contract_types.get(ctype, 0) + 1

        print("📊 Contract type distribution:")
        for ctype, count in contract_types.items():
            print(f"  {ctype}: {count} contracts")

        return contracts

    except Exception as e:
        print(f"❌ Error in fetch_all_contracts_in_region: {e}")
        import traceback
        traceback.print_exc()
        return []


async def debug_expand_all_contracts(contracts: List[Dict[str, Any]]):
    """Debug the expand_all_contracts function."""
    print("\n" + "=" * 80)
    print("DEBUGGING: expand_all_contracts")
    print("=" * 80)

    if not contracts:
        print("❌ No contracts to expand")
        return []

    # Take a small sample for debugging
    sample_size = min(10, len(contracts))
    sample_contracts = contracts[:sample_size]

    print(f"Expanding {sample_size} sample contracts...")

    try:
        expanded = await expand_all_contracts(sample_contracts)

        print(f"✅ Successfully expanded {len(expanded)} contracts")

        # Show expanded details
        print("\n📋 Expanded contract details:")
        for i, contract in enumerate(expanded):
            print(f"  Contract {i+1} (ID: {contract.get('contract_id')}):")
            print(f"    Issuer Name: {contract.get('issuer_name', 'Unknown')}")
            print(f"    Corp Name: {contract.get('issuer_corporation_name', 'Unknown')}")
            print(f"    Items: {contract.get('item_count', 0)} items")

            if contract.get('items'):
                for j, item in enumerate(contract['items'][:2]):  # Show first 2 items
                    print(f"      Item {j+1}: {item.get('name', 'Unknown')} (x{item.get('quantity', 1)})")
                    if item.get('blueprint_type'):
                        print(f"        Type: {item['blueprint_type']}")
                        if item.get('time_efficiency') is not None:
                            print(f"        TE: {item['time_efficiency']}%, ME: {item['material_efficiency']}%")
            print()

        return expanded

    except Exception as e:
        print(f"❌ Error in expand_all_contracts: {e}")
        import traceback
        traceback.print_exc()
        return []


async def debug_fetch_and_expand_all_forge_contracts():
    """Debug the fetch_and_expand_all_forge_contracts function."""
    print("\n" + "=" * 80)
    print("DEBUGGING: fetch_and_expand_all_forge_contracts")
    print("=" * 80)

    try:
        print("Fetching and expanding all Forge contracts...")
        expanded_contracts = await fetch_and_expand_all_forge_contracts()

        print(f"✅ Successfully fetched and expanded {len(expanded_contracts)} contracts")

        # Check cache file
        cache_file = os.path.join(os.path.dirname(__file__), "cache", "all_contracts_forge.json")
        if os.path.exists(cache_file):
            cache_size = os.path.getsize(cache_file)
            print(f"📁 Cache file size: {cache_size:,} bytes")

            # Load and verify cache
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                print(f"📁 Cache contains {len(cached_data)} contracts")
            except Exception as e:
                print(f"❌ Error reading cache: {e}")
        else:
            print("❌ Cache file does not exist")

        # Analyze expanded contracts
        print("\n📊 Analysis of expanded contracts:")
        blueprint_contracts = 0
        item_exchange_contracts = 0
        contracts_with_items = 0

        for contract in expanded_contracts:
            if contract.get('type') == 'item_exchange':
                item_exchange_contracts += 1
                if contract.get('items'):
                    contracts_with_items += 1
                    # Check for blueprints
                    for item in contract['items']:
                        if item.get('blueprint_type'):
                            blueprint_contracts += 1
                            break

        print(f"  Total contracts: {len(expanded_contracts)}")
        print(f"  Item exchange contracts: {item_exchange_contracts}")
        print(f"  Contracts with items: {contracts_with_items}")
        print(f"  Blueprint contracts: {blueprint_contracts}")

        return expanded_contracts

    except Exception as e:
        print(f"❌ Error in fetch_and_expand_all_forge_contracts: {e}")
        import traceback
        traceback.print_exc()
        return []


async def debug_contract_items_fetching():
    """Debug fetching contract items for a few sample contracts."""
    print("\n" + "=" * 80)
    print("DEBUGGING: Contract Items Fetching")
    print("=" * 80)

    try:
        # Get a few contracts to test item fetching
        contracts = await fetch_public_contracts_async(FORGE_REGION_ID, page=1)
        if not contracts:
            print("❌ No contracts found for testing")
            return

        # Test item fetching for first 3 item_exchange contracts
        tested = 0
        for contract in contracts:
            if contract.get('type') == 'item_exchange' and tested < 3:
                contract_id = contract.get('contract_id')
                print(f"\n🔍 Testing contract {contract_id}...")

                try:
                    items = await fetch_public_contract_items_async(contract_id)
                    if items:
                        print(f"  ✅ Found {len(items)} items:")
                        for i, item in enumerate(items):
                            type_id = item.get('type_id')
                            quantity = item.get('quantity', 1)
                            is_bpc = item.get('is_blueprint_copy', False)
                            print(f"    Item {i+1}: Type {type_id}, Quantity {quantity}, BPC: {is_bpc}")
                    else:
                        print("  ⚠️ No items found")
                except Exception as e:
                    print(f"  ❌ Error fetching items: {e}")

                tested += 1

    except Exception as e:
        print(f"❌ Error in contract items testing: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main debug function."""
    print("🚀 Starting contract fetching, storing, and expanding debug")
    print(f"Working directory: {os.getcwd()}")

    # Test individual components
    contracts = await debug_fetch_all_contracts_in_region()
    await debug_expand_all_contracts(contracts)
    await debug_contract_items_fetching()

    # Test the full pipeline
    await debug_fetch_and_expand_all_forge_contracts()

    print("\n🎉 Debug complete!")


if __name__ == "__main__":
    asyncio.run(main())