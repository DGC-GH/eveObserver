#!/usr/bin/env python3
"""
Find actual BPO competitors for our contract
"""

import asyncio
import sys
import os

# Add the scripts directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from api_client import fetch_public_contracts_async, fetch_public_contract_items_async

async def find_bpo_competitors():
    """Find contracts for the same BPO (type_id 29050) that are cheaper"""
    region_id = 10000002  # The Forge
    target_type_id = 29050
    our_price = 248990000.00

    print(f"Searching for BPO competitors in The Forge region...")
    print(f"Target: Type ID {target_type_id}, Max price: {our_price:,.2f} ISK")
    print("=" * 60)

    competitors_found = []
    page = 1

    while page <= 20:  # Check more pages to be thorough
        contracts_page = await fetch_public_contracts_async(region_id, page)
        if not contracts_page:
            break

        print(f"Checking page {page}...")

        for contract in contracts_page:
            contract_id = contract.get("contract_id")
            price = contract.get("price", 0)

            # Only check contracts cheaper than ours
            if price > 0 and price < our_price:
                # Get contract items
                items = await fetch_public_contract_items_async(contract_id)
                if items and len(items) == 1:
                    item = items[0]
                    type_id = item.get("type_id")
                    quantity = item.get("quantity", 1)
                    is_blueprint_copy = item.get("is_blueprint_copy", False)

                    # Check if it's the same BPO (not BPC)
                    if type_id == target_type_id and quantity == 1 and not is_blueprint_copy:
                        price_per_item = price / quantity
                        competitors_found.append({
                            'contract_id': contract_id,
                            'price': price,
                            'price_per_item': price_per_item,
                            'issuer_id': contract.get('issuer_id')
                        })
                        print(f"  FOUND BPO COMPETITOR: Contract {contract_id} - {price_per_item:,.2f} ISK")

        if len(contracts_page) < 1000:
            break
        page += 1

    print(f"\n{'=' * 60}")
    print(f"RESULTS: Found {len(competitors_found)} BPO competitors cheaper than {our_price:,.2f} ISK")

    if competitors_found:
        best_competitor = min(competitors_found, key=lambda x: x['price_per_item'])
        print(f"\nBEST COMPETITOR:")
        print(f"  Contract ID: {best_competitor['contract_id']}")
        print(f"  Price: {best_competitor['price_per_item']:,.2f} ISK per item")
        print(f"  Undercut by: {our_price - best_competitor['price_per_item']:,.2f} ISK")
    else:
        print("  No BPO competitors found - your contract is the cheapest BPO!")

if __name__ == "__main__":
    asyncio.run(find_bpo_competitors())