#!/usr/bin/env python3
"""
Debug script for contract competition checking functionality.
Manually tests the competition logic to verify we're getting real contracts and comparing prices correctly.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, List, Any, Optional

# Add the scripts directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

from api_client import (
    fetch_public_contracts_async,
    fetch_public_contract_items_async,
    get_session
)
from contract_processor import get_region_from_location

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def check_specific_contract_exists(contract_id: int, region_id: int):
    """
    Check if a specific contract exists and get its details.
    """
    print(f"\nChecking if contract {contract_id} exists in region {region_id}...")

    page = 1
    while True:
        contracts_page = await fetch_public_contracts_async(region_id, page)
        if contracts_page is None:
            print(f"ERROR: Failed to fetch contracts for region {region_id}, page {page}")
            break

        for contract in contracts_page:
            if contract.get("contract_id") == contract_id:
                print(f"FOUND contract {contract_id}:")
                print(f"  Type: {contract.get('type')}")
                print(f"  Status: {contract.get('status')}")
                print(f"  Price: {contract.get('price', 0):,.2f} ISK")
                print(f"  Issuer ID: {contract.get('issuer_id')}")
                print(f"  Start Location: {contract.get('start_location_id')}")

                # Fetch items for this contract
                items = await fetch_public_contract_items_async(contract_id)
                if items:
                    print(f"  Items: {len(items)}")
                    for item in items:
                        print(f"    - Type ID: {item.get('type_id')}, Quantity: {item.get('quantity')}")
                else:
                    print("  Items: None found")

                return contract

        if len(contracts_page) < 1000:
            break
        page += 1
        if page > 10:  # Safety limit
            break

    print(f"Contract {contract_id} not found in region {region_id}")
    return None


async def debug_contract_competition(contract_id: int, type_id: int, contract_price: float, quantity: int, start_location_id: int, is_blueprint_copy: bool = False):
    print(f"\n{'='*80}")
    print(f"DEBUGGING CONTRACT COMPETITION FOR CONTRACT {contract_id}")
    print(f"{'='*80}")

    print(f"Contract details:")
    print(f"  Contract ID: {contract_id}")
    print(f"  Type ID: {type_id}")
    print(f"  Total Price: {contract_price:,.2f} ISK")
    print(f"  Quantity: {quantity}")
    print(f"  Price per item: {contract_price/quantity:,.2f} ISK")
    print(f"  Start Location ID: {start_location_id}")

    # Get the region
    print(f"\nGetting region from location {start_location_id}...")
    region_id = await get_region_from_location(start_location_id)
    if not region_id:
        print(f"ERROR: Could not determine region for location {start_location_id}")
        return

    print(f"Region ID: {region_id}")

    # Calculate our price per item
    price_per_item = contract_price / quantity
    print(f"\nOur contract price per item: {price_per_item:,.2f} ISK")

    # Fetch competing contracts
    print(f"\nFetching competing contracts in region {region_id}...")
    page = 1
    competing_contracts = []
    total_pages_checked = 0

    while True:
        print(f"  Fetching page {page}...")
        contracts_page = await fetch_public_contracts_async(region_id, page)
        if contracts_page is None:
            print(f"    ERROR: Failed to fetch contracts for region {region_id}, page {page}")
            break
        elif not contracts_page:
            print(f"    No contracts returned for region {region_id}, page {page}")
            break

        print(f"    Fetched {len(contracts_page)} contracts from page {page}")

        # Filter for outstanding item_exchange contracts (excluding our own)
        page_competing = []
        for contract in contracts_page:
            if (
                contract.get("type") == "item_exchange"
                and contract.get("contract_id") != contract_id
                and contract.get("issuer_id") != 90045731  # Our character ID from logs
            ):
                page_competing.append(contract)

        competing_contracts.extend(page_competing)
        print(f"    Found {len(page_competing)} potential competing contracts on this page")

        # Check if there are more pages
        if len(contracts_page) < 1000:  # ESI returns max 1000 per page
            break
        page += 1
        total_pages_checked += 1

        # Safety limit to prevent infinite loops (same as real function)
        if page > 10:
            print(f"    Reached page limit (10) for debugging, stopping")
            break

    print(f"\nTotal competing contracts found: {len(competing_contracts)}")
    print(f"Total pages checked: {total_pages_checked + 1}")

    # Now fetch items for competing contracts and check prices
    print(f"\nAnalyzing competing contracts...")
    cheaper_contracts = []
    target_contract_found = False

    # OPTIMIZATION: Filter contracts by price first - only check contracts cheaper than ours
    price_filtered_contracts = []
    for contract in competing_contracts:
        contract_price = contract.get("price", 0)
        if contract_price > 0 and contract_price < price_per_item:  # Only check cheaper contracts
            price_filtered_contracts.append(contract)

    print(f"After price filtering: {len(price_filtered_contracts)} contracts cheaper than ours (from {len(competing_contracts)} total)")

    # Use concurrent fetching like the real implementation
    contracts_to_check = price_filtered_contracts[:100]  # Limit for debugging but use concurrent approach

    if contracts_to_check:
        print(f"Fetching items for {len(contracts_to_check)} price-filtered contracts concurrently...")

        # Fetch items concurrently (like the real check_contract_competition function)
        competing_tasks = []
        for comp_contract in contracts_to_check:
            comp_contract_id = comp_contract.get("contract_id")
            competing_tasks.append(fetch_public_contract_items_async(comp_contract_id))

        competing_items_results = await asyncio.gather(*competing_tasks, return_exceptions=True)

        # Process results
        for comp_contract, comp_items_result in zip(contracts_to_check, competing_items_results):
            if isinstance(comp_items_result, Exception):
                continue

            comp_items = comp_items_result
            if not comp_items or len(comp_items) != 1:
                continue  # Only check single-item contracts

            comp_contract_id = comp_contract.get("contract_id")
            comp_price = comp_contract.get("price", 0)
            comp_item = comp_items[0]
            comp_type_id = comp_item.get("type_id")
            comp_quantity = comp_item.get("quantity", 1)
            comp_is_blueprint_copy = comp_item.get("is_blueprint_copy", False)

            # Check if this is the specific contract that outbid ours
            if comp_contract_id == 222262092:
                print(f"    *** FOUND THE KNOWN COMPETITOR CONTRACT {comp_contract_id} ***")
                print(f"    Item: type_id={comp_type_id}, quantity={comp_quantity}, is_blueprint_copy={comp_is_blueprint_copy}")
                target_contract_found = True

            if comp_type_id == type_id and comp_quantity > 0 and comp_price > 0 and comp_is_blueprint_copy == is_blueprint_copy:
                comp_price_per_item = comp_price / comp_quantity
                print(f"  Found matching competitor: Contract {comp_contract_id} at {comp_price_per_item:,.2f} ISK per item")

                if comp_price_per_item < price_per_item:
                    print(f"    *** THIS CONTRACT UNDERCUTS OURS! ***")
                    cheaper_contracts.append({
                        'contract_id': comp_contract_id,
                        'price_per_item': comp_price_per_item,
                        'total_price': comp_price,
                        'quantity': comp_quantity
                    })
                    # In real implementation, we could return here, but for debugging let's collect all
                else:
                    print(f"    This contract is more expensive than ours")
            else:
                if comp_contract_id == 222262092:
                    print(f"    Contract doesn't match our criteria (wrong type_id, quantity, or blueprint type)")

    print(f"\nChecked {len(contracts_to_check)} price-filtered contracts concurrently")

    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Our contract {contract_id}: {price_per_item:,.2f} ISK per item")
    print(f"Target competitor contract 222262092 found: {target_contract_found}")
    print(f"Found {len(cheaper_contracts)} cheaper competing contracts:")

    for comp in cheaper_contracts:
        print(f"  Contract {comp['contract_id']}: {comp['price_per_item']:,.2f} ISK per item "
              f"(total: {comp['total_price']:,.2f} ISK, qty: {comp['quantity']})")

    if cheaper_contracts:
        best_competitor = min(cheaper_contracts, key=lambda x: x['price_per_item'])
        print(f"\nBest competitor: Contract {best_competitor['contract_id']} at "
              f"{best_competitor['price_per_item']:,.2f} ISK per item")
        print(f"Our contract is outbid by {price_per_item - best_competitor['price_per_item']:,.2f} ISK per item")
    else:
        print("  No cheaper contracts found - our contract is the cheapest!")


async def main():
    """
    Main debug function. Test with a specific contract from the logs.
    """
    # Test with contract 222641828 from the logs
    # Contract details from logs:
    # - Contract ID: 222641828
    # - Type ID: 29050
    # - Price per item: 248990000.00
    # - Region: 10000002 (The Forge)
    # - Was outbid by contract 222262092 with price_per_item: 7760000.00

    # We need to estimate the original contract details
    # From logs: price_per_item was 248990000.00, let's assume quantity = 1 for BPO
    contract_id = 222641828
    type_id = 29050
    price_per_item = 248990000.00
    quantity = 1  # Assuming BPO
    contract_price = price_per_item * quantity
    start_location_id = 60003760  # Jita IV - Moon 4 - Caldari Navy Assembly Plant (common location)
    is_blueprint_copy = False  # This is a BPO, not a BPC

    # First check if the competitor contract still exists
    region_id = 10000002  # The Forge
    competitor_contract = await check_specific_contract_exists(222262092, region_id)
    if competitor_contract:
        print(f"\nCompetitor contract 222262092 still exists!")
    else:
        print(f"\nCompetitor contract 222262092 no longer exists (expired/fulfilled/deleted)")

    # Now run the competition analysis
    await debug_contract_competition(
        contract_id=contract_id,
        type_id=type_id,
        contract_price=contract_price,
        quantity=quantity,
        start_location_id=start_location_id,
        is_blueprint_copy=is_blueprint_copy
    )


if __name__ == "__main__":
    asyncio.run(main())