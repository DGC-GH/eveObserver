#!/usr/bin/env python3
"""Debug script to test fetching public contracts from region 10000002."""

import asyncio
import sys
import os

# Add the scripts directory to the path so we can import from fetch_data.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fetch_data import fetch_public_contracts, fetch_public_contract_items

async def debug_contract_fetching():
    """Debug fetching public contracts from region 10000002."""
    region_id = 10000002  # The Forge
    print(f"Fetching public contracts from region {region_id}...")

    page = 1
    total_contracts = 0
    item_exchange_count = 0
    outstanding_count = 0

    while True:
        contracts_page = await fetch_public_contracts(region_id, page)
        if not contracts_page:
            print(f"No contracts returned on page {page}")
            break

        print(f"Page {page}: {len(contracts_page)} contracts")

        for i, contract in enumerate(contracts_page):
            if i >= 1:  # Only check first contract
                break
            total_contracts += 1
            print(f"Full contract data: {contract}")
            contract_type = contract.get('type')
            status = contract.get('status')
            contract_id = contract.get('contract_id')

            if contract_type == 'item_exchange':
                item_exchange_count += 1
                status_str = str(status)
                print(f"item_exchange contract: {contract_id}, status: {status_str}")
                # Check if status is None or missing
                if status is None or status == 'outstanding':
                    outstanding_count += 1
                    print(f"Considering as outstanding: {contract_id}")

                    # Fetch items for this contract
                    items = await fetch_public_contract_items(contract_id)
                    if items:
                        if len(items) == 1:
                            item = items[0]
                            type_id = item.get('type_id')
                            quantity = item.get('quantity', 1)
                            print(f"  Single item: type_id={type_id}, quantity={quantity}")
                        else:
                            print(f"  Multiple items: {len(items)}")
                    else:
                        print("  No items found")

        # Check if there are more pages
        if len(contracts_page) < 1000:  # ESI returns max 1000 per page
            break
        page += 1

        # Limit to first page for debugging
        if page >= 1:
            print("Stopping after 1 page for debugging")
            break

    print("\nSummary:")
    print(f"Total contracts fetched: {total_contracts}")
    print(f"item_exchange contracts: {item_exchange_count}")
    print(f"Outstanding item_exchange contracts: {outstanding_count}")

if __name__ == "__main__":
    asyncio.run(debug_contract_fetching())