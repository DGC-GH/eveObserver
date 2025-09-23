#!/usr/bin/env python3
"""
Debug script for contract competition checking functionality.
Tests 3 of the user's contracts to check if they have been outbid.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, List, Any, Optional, Tuple

# Add the scripts directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

from api_client import (
    fetch_esi,
    fetch_public_esi,
    fetch_public_contracts_async,
    fetch_public_contract_items_async,
    get_session,
    wp_request,
    refresh_token,
    cleanup_session
)
from contract_processor import check_contract_competition_hybrid, get_region_from_location, get_issuer_names
from config import TOKENS_FILE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_tokens():
    """Load stored tokens."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return {}


async def get_user_contracts():
    """Fetch contracts for debugging - try corporation contracts first, fallback to public"""
    from esi_oauth import load_tokens, save_tokens
    from datetime import datetime, timezone

    tokens = load_tokens()
    if not tokens:
        logger.warning("No tokens found, falling back to public contracts")
        return await get_public_contracts_for_debug()

    # Find Dr FiLiN's token (assuming it's the first one or we can identify by name)
    dr_filin_token = None
    dr_filin_char_id = None
    for char_id, token_data in tokens.items():
        if token_data.get("name", "").lower() == "dr filin":
            dr_filin_token = token_data
            dr_filin_char_id = int(char_id)
            break

    if not dr_filin_token:
        logger.warning("Dr FiLiN's token not found, falling back to public contracts")
        return await get_public_contracts_for_debug()

    # Check if token is expired and refresh if needed
    try:
        expired = datetime.now(timezone.utc) > datetime.fromisoformat(
            dr_filin_token.get("expires_at", "2000-01-01T00:00:00+00:00")
        )
    except (ValueError, TypeError):
        expired = True

    if expired:
        logger.info("Dr FiLiN's token expired, refreshing...")
        new_token = refresh_token(dr_filin_token["refresh_token"])
        if new_token:
            dr_filin_token.update(new_token)
            save_tokens(tokens)
            logger.info("Token refreshed successfully")
        else:
            logger.warning("Failed to refresh token, falling back to public contracts")
            return await get_public_contracts_for_debug()

    access_token = dr_filin_token["access_token"]
    char_name = dr_filin_token["name"]

    # Try to get corporation contracts
    try:
        # First get character data to find corporation
        char_data = await fetch_esi(f"/characters/{dr_filin_char_id}/", dr_filin_char_id, access_token)
        if not char_data or 'corporation_id' not in char_data:
            logger.warning("Could not get corporation ID, falling back to public contracts")
            return await get_public_contracts_for_debug()

        corp_id = char_data['corporation_id']
        logger.info(f"Fetching corporation contracts for {char_name} (corp ID: {corp_id})")

        # Fetch corporation contracts
        corp_contracts = await fetch_esi(f"/corporations/{corp_id}/contracts/", corp_id, access_token)
        if corp_contracts:
            # Filter for outstanding item_exchange contracts from this corporation
            outstanding_item_exchange = [
                c for c in corp_contracts
                if c.get("status") == "outstanding" and c.get("type") == "item_exchange" and c.get("issuer_corporation_id") == corp_id
            ]
            logger.info(f"Found {len(outstanding_item_exchange)} outstanding item exchange contracts from corporation {corp_id}")
            return outstanding_item_exchange[:10]  # Limit to first 10 for debugging
        else:
            logger.warning("No corporation contracts found, falling back to public contracts")
            return await get_public_contracts_for_debug()

    except Exception as e:
        logger.warning(f"Failed to fetch corporation contracts: {e}, falling back to public contracts")
        return await get_public_contracts_for_debug()


async def get_public_contracts_for_debug():
    """Fallback function to get some public contracts for debugging when corporation access fails."""
    logger.info("Fetching public contracts for debugging...")

    # Get some public contracts from a busy region (like The Forge)
    region_id = 10000002  # The Forge region
    public_contracts = await fetch_public_contracts_async(region_id, page=1)

    if not public_contracts:
        logger.warning("No public contracts found")
        return []

    # Filter for item exchange contracts and get first 3
    item_exchange_contracts = [
        c for c in public_contracts
        if c.get("type") == "item_exchange"
    ][:3]

    detailed_contracts = []
    for contract in item_exchange_contracts:
        contract_id = contract["contract_id"]

        # Get contract items
        contract_items = await fetch_public_contract_items_async(contract_id)
        if not contract_items:
            continue

        # Get first item details
        first_item = contract_items[0]
        type_id = first_item.get("type_id")
        quantity = first_item.get("quantity", 1)
        is_blueprint_copy = first_item.get("is_blueprint_copy", False)

        # Get item name
        type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
        item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"

        detailed_contracts.append({
            'contract_data': contract,
            'contract_items': contract_items,
            'item_name': item_name,
            'type_id': type_id,
            'quantity': quantity,
            'is_blueprint_copy': is_blueprint_copy,
            'total_items': len(contract_items),
            'price_per_item': contract.get("price", 0) / quantity if quantity > 0 else 0,
            'contract_id': contract_id
        })

    logger.info(f"Found {len(detailed_contracts)} public contracts for debugging")
    return detailed_contracts


async def check_contract_outbid_status(contract_data: Dict[str, Any], contract_items: List[Dict[str, Any]]) -> Tuple[bool, Optional[float]]:
    """Check if a contract has been outbid."""
    try:
        is_outbid, competing_price, debug_info = await check_contract_competition_hybrid(contract_data, contract_items)
        if debug_info:
            print(f"  Debug: Found {len(debug_info)} total competing contracts in region")
        return is_outbid, competing_price
    except Exception as e:
        logger.error(f"Error checking contract competition: {e}")
        return False, None


async def check_contract_outbid_status_with_filter(contract_data: Dict[str, Any], contract_items: List[Dict[str, Any]], issuer_name_filter: str) -> Tuple[bool, Optional[float]]:
    """Check if a contract has been outbid, filtering by issuer name."""
    try:
        is_outbid, competing_price, debug_info = await check_contract_competition_hybrid(contract_data, contract_items, issuer_name_filter=issuer_name_filter)
        if debug_info:
            print(f"  Debug: Found {len(debug_info)} total competing contracts in region (filtered by '{issuer_name_filter}')")
        return is_outbid, competing_price
    except Exception as e:
        logger.error(f"Error checking contract competition with filter: {e}")
        return False, None


async def find_capital_ion_thruster_contract():
    """Find any Capital Ion Thruster Blueprint contract for testing."""
    print("🔍 Searching for any Capital Ion Thruster Blueprint contract...")

    # First, let's try to find the type ID by searching for known capital thruster blueprints
    # Common capital thruster blueprint type IDs
    possible_type_ids = [23713, 23714, 23715, 23716, 23717]  # Some capital thruster BPOs

    capital_ion_type_id = None
    for type_id in possible_type_ids:
        try:
            type_data = await fetch_public_esi(f'/universe/types/{type_id}')
            if type_data:
                name = type_data.get('name', '')
                print(f'Checking {type_id}: {name}')
                if 'Capital Ion Thruster' in name and 'Blueprint' in name:
                    capital_ion_type_id = type_id
                    print(f'*** FOUND: {name} = {type_id} ***')
                    break
        except:
            continue

    if not capital_ion_type_id:
        print("❌ Could not find Capital Ion Thruster Blueprint type ID")
        return None

    print(f"📋 Found Capital Ion Thruster Blueprint type ID: {capital_ion_type_id}")

    # Search for contracts containing this blueprint
    regions_to_check = [
        10000002,  # The Forge (Jita)
    ]

    for region_id in regions_to_check:
        print(f"🔍 Checking region {region_id} for Capital Ion Thruster Blueprint contracts...")

        # Check first few pages
        for page in range(1, 6):
            try:
                contracts = await fetch_public_contracts_async(region_id, page)
                if not contracts:
                    break

                for contract in contracts:
                    if contract.get("type") != "item_exchange" or contract.get("status") != "outstanding":
                        continue

                    contract_id = contract.get("contract_id")

                    # Get contract items
                    contract_items = await fetch_public_contract_items_async(contract_id)
                    if not contract_items or len(contract_items) != 1:
                        continue

                    item = contract_items[0]
                    if item.get("type_id") == capital_ion_type_id and item.get("quantity") == -1:  # BPO
                        print(f"🎯 Found Capital Ion Thruster Blueprint contract: {contract_id}")
                        print(f"   Region: {region_id}")
                        print(f"   Price: {contract.get('price', 0):,.2f} ISK")
                        print(f"   Issuer ID: {contract.get('issuer_id')}")
                        print(f"   Issuer Corp ID: {contract.get('issuer_corporation_id')}")
                        print(f"   Title: {contract.get('title', 'N/A')}")

                        return {
                            'contract_data': contract,
                            'contract_items': contract_items,
                            'region_id': region_id,
                            'type_id': capital_ion_type_id
                        }

            except Exception as e:
                print(f"Error checking page {page} in region {region_id}: {e}")
                break

    print("❌ No Capital Ion Thruster Blueprint contracts found in major trade hubs")
    return None


async def test_issuer_name_filtering():
    """Test the issuer name filtering functionality."""
    print("\n" + "=" * 80)
    print("TESTING ISSUER NAME FILTERING")
    print("=" * 80)

    # Find the Capital Ion Thruster Blueprint contract
    contract_info = await find_capital_ion_thruster_contract()
    if not contract_info:
        print("Could not find the Capital Ion Thruster Blueprint contract to test with.")
        return

    contract_data = contract_info['contract_data']
    contract_items = contract_info['contract_items']
    contract_id = contract_data.get('contract_id')

    print(f"\n📋 Testing with Capital Ion Thruster Blueprint contract {contract_id}")
    print(f"   Price: {contract_data.get('price', 0):,.2f} ISK")

    # Test 1: Check competition without filtering
    print(f"\n🔍 Test 1: Checking competition WITHOUT issuer name filtering...")
    is_outbid, competing_price = await check_contract_outbid_status(contract_data, contract_items)

    if is_outbid:
        print(f"   ❌ OUTBID! Cheapest competitor: {competing_price:,.2f} ISK")
    else:
        print(f"   ✅ Not outbid - appears to be the cheapest!")

    # Test 2: Check competition with "Research Magic" filtering
    print(f"\n🔍 Test 2: Checking competition WITH 'Research Magic' issuer name filtering...")
    is_outbid_filtered, competing_price_filtered = await check_contract_outbid_status_with_filter(
        contract_data, contract_items, "Research Magic"
    )

    if is_outbid_filtered:
        print(f"   ❌ OUTBID by Research Magic! Cheapest competitor: {competing_price_filtered:,.2f} ISK")
        print(f"   This confirms the contract is outbid by Research Magic traders!")
    else:
        print(f"   ✅ Not outbid by Research Magic - no cheaper Research Magic contracts found")

    # Test 3: Show detailed competitor analysis
    print(f"\n🔍 Test 3: Detailed competitor analysis for Research Magic...")
    await detailed_competitor_analysis(contract_data, contract_items, "Research Magic")


async def detailed_competitor_analysis(contract_data: Dict[str, Any], contract_items: List[Dict[str, Any]], issuer_name_filter: str):
    """Perform detailed analysis of competitors with issuer name filtering."""
    from contract_processor import check_contract_competition

    if not contract_items or len(contract_items) != 1:
        print("   Detailed analysis only works for single-item contracts")
        return

    item = contract_items[0]
    type_id = item.get("type_id")
    quantity = item.get("quantity", 1)
    contract_price = contract_data.get("price", 0)
    contract_id = contract_data.get("contract_id")

    if quantity <= 0 or contract_price <= 0:
        print("   Invalid contract data for analysis")
        return

    price_per_item = contract_price / quantity

    # Get contract region
    region_id = await get_region_from_location(contract_data.get("start_location_id"))
    if not region_id:
        print("   Could not determine contract region")
        return

    print(f"   Contract region: {region_id}")
    print(f"   Contract price per item: {price_per_item:,.2f} ISK")
    print(f"   Looking for competitors from issuers containing '{issuer_name_filter}'...")

    # Manually check competitors with detailed logging
    found_research_magic_competitors = []

    for page in range(1, 6):  # Check first 5 pages
        try:
            contracts_page = await fetch_public_contracts_async(region_id, page, sort_by_price=True)
            if not contracts_page:
                break

            for contract in contracts_page:
                comp_contract_id = contract.get("contract_id")
                comp_price = contract.get("price", 0)
                comp_issuer_id = contract.get("issuer_id")
                comp_issuer_corp_id = contract.get("issuer_corporation_id")
                comp_title = contract.get("title", "")

                # Quick filters
                if contract.get("type") != "item_exchange" or contract.get("status") != "outstanding":
                    continue
                if comp_contract_id == contract_id:
                    continue

                # Check if issuer name contains our filter
                issuer_names = await get_issuer_names([comp_issuer_id, comp_issuer_corp_id] if comp_issuer_corp_id else [comp_issuer_id])
                issuer_name = issuer_names.get(comp_issuer_id, "")
                corp_name = issuer_names.get(comp_issuer_corp_id, "") if comp_issuer_corp_id else ""

                name_matches = (
                    issuer_name_filter.lower() in issuer_name.lower() or
                    issuer_name_filter.lower() in corp_name.lower() or
                    issuer_name_filter.lower() in comp_title.lower()
                )

                if not name_matches:
                    continue

                # Get contract items to verify it's the same blueprint
                try:
                    comp_items = await fetch_public_contract_items_async(comp_contract_id)
                    if not comp_items or len(comp_items) != 1:
                        continue

                    comp_item = comp_items[0]
                    if (comp_item.get("type_id") == type_id and
                        comp_item.get("is_blueprint_copy") == item.get("is_blueprint_copy")):

                        if comp_price > 0:
                            comp_price_per_item = comp_price / comp_item.get("quantity", 1)
                            found_research_magic_competitors.append({
                                'contract_id': comp_contract_id,
                                'price_per_item': comp_price_per_item,
                                'issuer_name': issuer_name,
                                'corp_name': corp_name,
                                'title': comp_title,
                                'issuer_id': comp_issuer_id,
                                'issuer_corp_id': comp_issuer_corp_id
                            })

                except Exception as e:
                    continue

        except Exception as e:
            break

    if found_research_magic_competitors:
        print(f"   🎯 Found {len(found_research_magic_competitors)} Research Magic competitors:")
        for comp in sorted(found_research_magic_competitors, key=lambda x: x['price_per_item']):
            print(f"      Contract {comp['contract_id']}: {comp['price_per_item']:,.2f} ISK")
            print(f"         Issuer: {comp['issuer_name']} (ID: {comp['issuer_id']})")
            if comp['corp_name']:
                print(f"         Corp: {comp['corp_name']} (ID: {comp['issuer_corp_id']})")
            if comp['title']:
                print(f"         Title: {comp['title']}")
            print(f"         Cheaper by: {price_per_item - comp['price_per_item']:,.2f} ISK")
            print()
    else:
        print(f"   ✅ No Research Magic competitors found for this contract")


async def main():
    """
    Main debug function. Test contracts for outbidding and issuer name filtering.
    """
    print("=" * 80)
    print("DEBUGGING CONTRACT COMPETITION - CAPITAL ION THRUSTER BLUEPRINT")
    print("=" * 80)

    # Test the issuer name filtering functionality
    await test_issuer_name_filtering()

    print("\n" + "=" * 80)
    print("GENERAL CONTRACT COMPETITION TESTING")
    print("=" * 80)

    # Get contracts (try corporation first, fallback to public)
    contracts = await get_user_contracts()

    if not contracts:
        print("No contracts found to test.")
        return

    print(f"Testing {len(contracts)} contracts:")
    print()

    for i, contract in enumerate(contracts, 1):
        contract_id = contract.get("contract_id")

        print(f"Contract {i}: Contract ID {contract_id}")
        print(f"  Type: {contract.get('type', 'unknown')}")
        print(f"  Status: {contract.get('status', 'unknown')}")
        print(f"  Price: {contract.get('price', 0):,.2f} ISK")

        # Get contract items to check competition
        try:
            # For corporation contracts, we need to get items
            if 'issuer_corporation_id' in contract:
                corp_id = contract['issuer_corporation_id']
                # We need a token to get items - this might fail if we don't have proper access
                tokens = load_tokens()
                access_token = None
                for char_id, token_data in tokens.items():
                    if token_data.get("name", "").lower() == "dr filin":
                        access_token = token_data.get("access_token")
                        break

                if access_token:
                    contract_items = await fetch_esi(f"/corporations/{corp_id}/contracts/{contract_id}/items/", corp_id, access_token)
                else:
                    contract_items = None
            else:
                # Public contract
                contract_items = await fetch_public_contract_items_async(contract_id)

            if not contract_items:
                print(f"  Could not get items for contract {contract_id} (may not have proper corporation roles)")
                print("-" * 60)
                continue

            # Check if single item
            if len(contract_items) == 1:
                item = contract_items[0]
                type_id = item.get("type_id")
                quantity = item.get("quantity", 1)

                # Get item name
                type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
                item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"

                price_per_item = contract.get("price", 0) / quantity if quantity > 0 else 0

                print(f"  Item: {item_name}")
                print(f"  Quantity: {quantity}")
                print(f"  Price per item: {price_per_item:,.2f} ISK")

                # Check competition
                print(f"  Checking for competitors...")
                is_outbid, competing_price = await check_contract_outbid_status(contract, contract_items)

                if is_outbid:
                    print(f"  ❌ OUTBID! Cheapest competitor: {competing_price:,.2f} ISK per item")
                    print(f"  Difference: {price_per_item - competing_price:,.2f} ISK per item")
                else:
                    print(f"  ✅ Not outbid - appears to be the cheapest!")
            else:
                print(f"  📦 Multi-item contract ({len(contract_items)} items) - competition check designed for single-item contracts")

        except Exception as e:
            print(f"  Error processing contract {contract_id}: {e}")

        print("-" * 60)
        print()

    # Cleanup session
    await cleanup_session()
    """
    Main debug function. Test contracts for outbidding.
    """
    print("=" * 80)
    print("DEBUGGING CONTRACT COMPETITION")
    print("=" * 80)

    # Get contracts (try corporation first, fallback to public)
    contracts = await get_user_contracts()

    if not contracts:
        print("No contracts found to test.")
        return

    print(f"Testing {len(contracts)} contracts:")
    print()

    for i, contract in enumerate(contracts, 1):
        contract_id = contract.get("contract_id")

        print(f"Contract {i}: Contract ID {contract_id}")
        print(f"  Type: {contract.get('type', 'unknown')}")
        print(f"  Status: {contract.get('status', 'unknown')}")
        print(f"  Price: {contract.get('price', 0):,.2f} ISK")

        # Get contract items to check competition
        try:
            # For corporation contracts, we need to get items
            if 'issuer_corporation_id' in contract:
                corp_id = contract['issuer_corporation_id']
                # We need a token to get items - this might fail if we don't have proper access
                tokens = load_tokens()
                access_token = None
                for char_id, token_data in tokens.items():
                    if token_data.get("name", "").lower() == "dr filin":
                        access_token = token_data.get("access_token")
                        break

                if access_token:
                    contract_items = await fetch_esi(f"/corporations/{corp_id}/contracts/{contract_id}/items/", corp_id, access_token)
                else:
                    contract_items = None
            else:
                # Public contract
                contract_items = await fetch_public_contract_items_async(contract_id)

            if not contract_items:
                print(f"  Could not get items for contract {contract_id} (may not have proper corporation roles)")
                print("-" * 60)
                continue

            # Check if single item
            if len(contract_items) == 1:
                item = contract_items[0]
                type_id = item.get("type_id")
                quantity = item.get("quantity", 1)

                # Get item name
                type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
                item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"

                price_per_item = contract.get("price", 0) / quantity if quantity > 0 else 0

                print(f"  Item: {item_name}")
                print(f"  Quantity: {quantity}")
                print(f"  Price per item: {price_per_item:,.2f} ISK")

                # Check competition
                print(f"  Checking for competitors...")
                is_outbid, competing_price = await check_contract_outbid_status(contract, contract_items)

                if is_outbid:
                    print(f"  ❌ OUTBID! Cheapest competitor: {competing_price:,.2f} ISK per item")
                    print(f"  Difference: {price_per_item - competing_price:,.2f} ISK per item")
                else:
                    print(f"  ✅ Not outbid - appears to be the cheapest!")
            else:
                print(f"  📦 Multi-item contract ({len(contract_items)} items) - competition check designed for single-item contracts")

        except Exception as e:
            print(f"  Error processing contract {contract_id}: {e}")

        print("-" * 60)
        print()

    # Cleanup session
    await cleanup_session()


if __name__ == "__main__":
    asyncio.run(main())