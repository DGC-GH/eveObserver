"""
EVE Observer Contract BPO Functions
Handles BPO-specific contract operations.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from api_client import fetch_public_esi
from config import CACHE_DIR
from contract_fetching import fetch_corporation_contracts

logger = logging.getLogger(__name__)


def save_bpo_contracts(contracts: List[Dict[str, Any]], filename: str):
    """Save BPO contracts to JSON file."""
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        json.dump(contracts, f, indent=2, default=str)
    logger.info(f"Saved {len(contracts)} BPO contracts to {filename}")


async def filter_single_bpo_contracts(contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter contracts to only single BPO contracts."""
    logger.info("Filtering for single BPO contracts...")
    single_bpo_contracts = []

    for contract in contracts:
        if contract.get("type") != "item_exchange":
            continue

        contract_id = contract["contract_id"]

        # Check if items are already in the contract data (from cache)
        contract_items = contract.get("items", [])
        if not contract_items or len(contract_items) != 1:
            continue

        item = contract_items[0]
        type_id = item.get("type_id")
        quantity = item.get("quantity", 1)
        is_blueprint_copy = item.get("is_blueprint_copy", False)

        if quantity == -1 and not is_blueprint_copy and type_id:
            # Get item name from the item data (should already be populated)
            item_name = item.get("name", f"Type {type_id}")

            bpo_contract = contract.copy()
            bpo_contract.update({"type_id": type_id, "item_name": item_name, "contract_items": contract_items})

            single_bpo_contracts.append(bpo_contract)
            logger.debug(f"Found single BPO contract {contract_id}: {item_name}")

    logger.info(f"Found {len(single_bpo_contracts)} single BPO contracts")
    return single_bpo_contracts


async def get_user_single_bpo_contracts() -> List[Dict[str, Any]]:
    """Get user's outstanding single BPO contracts."""
    from datetime import datetime, timezone

    from esi_oauth import load_tokens, save_tokens

    tokens = load_tokens()
    if not tokens:
        logger.warning("No tokens found")
        return []

    # Find Dr FiLiN's token
    dr_filin_token = None
    dr_filin_char_id = None
    for char_id, token_data in tokens.items():
        if token_data.get("name", "").lower() == "dr filin":
            dr_filin_token = token_data
            dr_filin_char_id = int(char_id)
            break

    if not dr_filin_token:
        logger.warning("Dr FiLiN's token not found")
        return []

    # Check if token is expired and refresh if needed
    try:
        expired = datetime.now(timezone.utc) > datetime.fromisoformat(
            dr_filin_token.get("expires_at", "2000-01-01T00:00:00+00:00")
        )
    except (ValueError, TypeError):
        expired = True

    if expired:
        logger.info("Dr FiLiN's token expired, refreshing...")
        from api_client import refresh_token

        new_token = refresh_token(dr_filin_token["refresh_token"])
        if new_token:
            dr_filin_token.update(new_token)
            save_tokens(tokens)
            logger.info("Token refreshed successfully")
        else:
            logger.warning("Failed to refresh token")
            return []

    access_token = dr_filin_token["access_token"]

    # Fetch corporation contracts
    try:
        # Get corporation ID
        char_data = await fetch_public_esi(f"/characters/{dr_filin_char_id}/")
        if not char_data or "corporation_id" not in char_data:
            logger.warning("Could not get corporation ID")
            return []

        corp_id = char_data["corporation_id"]
        logger.info(f"Fetching corporation contracts for corp ID: {corp_id}")

        corp_contracts = await fetch_corporation_contracts(corp_id, access_token)
        if not corp_contracts:
            logger.warning("No corporation contracts found")
            return []

        # Filter for outstanding item_exchange contracts
        outstanding_item_exchange = [
            c for c in corp_contracts if c.get("status") == "outstanding" and c.get("type") == "item_exchange"
        ]

        user_bpo_contracts = []

        for contract in outstanding_item_exchange:
            contract_id = contract["contract_id"]

            # Get contract items
            from contract_fetching import fetch_corporation_contract_items

            contract_items = await fetch_corporation_contract_items(corp_id, contract_id, access_token)

            if not contract_items or len(contract_items) != 1:
                continue

            item = contract_items[0]
            type_id = item.get("type_id")
            quantity = item.get("quantity", 1)
            is_blueprint_copy = item.get("is_blueprint_copy", False)

            if quantity == -1 and not is_blueprint_copy and type_id:
                # Get item name
                type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
                item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"
                user_contract = {
                    "contract_id": contract_id,
                    "type_id": type_id,
                    "item_name": item_name,
                    "price": contract.get("price", 0),
                    "contract_data": contract,
                    "contract_items": contract_items,
                }

                user_bpo_contracts.append(user_contract)

        logger.info(f"Found {len(user_bpo_contracts)} user single BPO contracts")
        return user_bpo_contracts

    except Exception as e:
        logger.error(f"Error fetching user contracts: {e}")
        return []


def compare_contracts(user_contracts: List[Dict[str, Any]], market_contracts: List[Dict[str, Any]]):
    """Compare user's contracts to market contracts to find cheaper alternatives."""
    logger.info("Comparing user contracts to market contracts...")

    for user_contract in user_contracts:
        user_type_id = user_contract["type_id"]
        user_price = user_contract["price"]
        user_contract_id = user_contract["contract_id"]
        item_name = user_contract["item_name"]

        # Find market contracts for the same BPO
        matching_market = [
            c for c in market_contracts if c["type_id"] == user_type_id and c["contract_id"] != user_contract_id
        ]

        if not matching_market:
            logger.info(f"No market contracts found for {item_name} (contract {user_contract_id})")
            continue

        # Sort by price ascending
        matching_market.sort(key=lambda x: x["price"])

        cheapest_market = matching_market[0]
        cheapest_price = cheapest_market["price"]

        if cheapest_price < user_price:
            price_diff = user_price - cheapest_price
            logger.warning(f"CHEAPER FOUND for {item_name}:")
            logger.warning(f"  Your contract {user_contract_id}: {user_price:,.2f} ISK")
            logger.warning(f"  Market contract {cheapest_market['contract_id']}: {cheapest_price:,.2f} ISK")
            logger.warning(f"  Price difference: {price_diff:,.2f} ISK")
            logger.warning(f"  Market issuer: {cheapest_market.get('issuer_id', 'Unknown')}")
            logger.warning(f"  Market title: {cheapest_market.get('title', 'N/A')}")
            logger.warning(f"  Contract data: {cheapest_market}")
            logger.warning("")
        else:
            logger.info(f"Your contract {user_contract_id} for {item_name} is the cheapest at {user_price:,.2f} ISK")
