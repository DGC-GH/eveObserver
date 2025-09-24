"""
EVE Observer Contract Processor
Main orchestrator for contract processing operations.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from api_client import validate_input_params
from blueprint_processor import (
    extract_blueprints_from_contracts,
    process_blueprints_parallel,
    update_blueprint_from_asset_in_wp,
)
from cache_manager import load_blueprint_cache, load_location_cache, load_structure_cache
from cache_manager_contracts import ContractCacheManager
from config import CACHE_DIR
from contract_bpo import get_user_single_bpo_contracts
from contract_competition import check_contracts_competition_concurrent
from contract_expansion import fetch_and_expand_all_forge_contracts
from contract_fetching import fetch_character_contracts
from contract_wordpress import batch_update_contracts_in_wp
from utils import parse_arguments

logger = logging.getLogger(__name__)

# Contract Processing Counter
contract_counter = 0


@validate_input_params(int, str, str, dict, dict, dict, dict, dict)
async def process_character_contracts(
    char_id: int,
    access_token: str,
    char_name: str,
    wp_post_id_cache: Dict[str, Any],
    blueprint_cache: Dict[str, Any],
    location_cache: Dict[str, Any],
    structure_cache: Dict[str, Any],
    failed_structures: Dict[str, Any],
) -> None:
    """
    Process contracts for a character.

    Fetches character contracts, processes blueprints from contract items,
    and creates/updates contract posts in WordPress.

    Args:
        char_id: Character ID to process contracts for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    logger.info(f"Starting contract processing for {char_name}")
    char_contracts = await fetch_character_contracts(char_id, access_token)
    if char_contracts:
        logger.info(f"Character contracts for {char_name}: {len(char_contracts)} items")

        # Process blueprints from contracts
        from blueprint_processor import extract_blueprints_from_contracts

        contract_blueprints = await extract_blueprints_from_contracts(char_contracts, "char", char_id)
        if contract_blueprints:
            logger.info(f"Character contract blueprints: {len(contract_blueprints)} items")
            # Process blueprints in parallel
            await process_blueprints_parallel(
                contract_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures,
            )

        # Fetch and expand all Forge contracts once for competition checking
        logger.info("Fetching all expanded contracts from The Forge region for competition analysis...")
        all_expanded_contracts = await fetch_and_expand_all_forge_contracts()

        # Collect contracts that need competition checking
        contracts_to_check = []
        contract_items_to_check = []

        # Collect all contracts that need updating
        contracts_to_update = []

        # Process contracts themselves
        for contract in char_contracts:
            contract_status = contract.get("status", "")
            if contract_status in ["finished", "deleted"]:
                # Skip finished/deleted contracts to improve performance
                continue
            elif contract_status == "expired":
                logger.info(f"EXPIRED CHARACTER CONTRACT TO DELETE MANUALLY: {contract['contract_id']}")

            # Check if this contract needs competition checking
            if contract.get("status") == "outstanding" and contract.get("type") == "item_exchange":
                # Fetch contract items for competition checking
                contract_items = None
                if all_expanded_contracts:
                    for expanded_contract in all_expanded_contracts:
                        if expanded_contract.get("contract_id") == contract["contract_id"]:
                            contract_items = expanded_contract.get("items", [])
                            break

                if contract_items:
                    contracts_to_check.append(contract)
                    contract_items_to_check.append(contract_items)
                else:
                    # No items available, still update the contract but without competition check
                    contracts_to_update.append(
                        {
                            "contract": contract,
                            "is_outbid": False,
                            "competing_price": None,
                            "for_corp": False,
                            "entity_id": char_id,
                            "access_token": access_token,
                            "blueprint_cache": blueprint_cache,
                            "all_expanded_contracts": all_expanded_contracts,
                        }
                    )
            else:
                # Not an outstanding sell contract, just update normally
                contracts_to_update.append(
                    {
                        "contract": contract,
                        "is_outbid": False,
                        "competing_price": None,
                        "for_corp": False,
                        "entity_id": char_id,
                        "access_token": access_token,
                        "blueprint_cache": blueprint_cache,
                        "all_expanded_contracts": all_expanded_contracts,
                    }
                )

        # Run competition checks concurrently for contracts that need them
        if contracts_to_check:
            logger.info(f"Running concurrent competition checks for {len(contracts_to_check)} contracts...")
            competition_results = await check_contracts_competition_concurrent(
                contracts_to_check, contract_items_to_check, all_expanded_contracts
            )

            # Add competition results to update list
            for contract, (is_outbid, competing_price) in zip(contracts_to_check, competition_results):
                contracts_to_update.append(
                    {
                        "contract": contract,
                        "is_outbid": is_outbid,
                        "competing_price": competing_price,
                        "for_corp": False,
                        "entity_id": char_id,
                        "access_token": access_token,
                        "blueprint_cache": blueprint_cache,
                        "all_expanded_contracts": all_expanded_contracts,
                    }
                )

        # Run all WordPress updates concurrently
        if contracts_to_update:
            logger.info(f"Running batched WordPress updates for {len(contracts_to_update)} contracts...")
            await batch_update_contracts_in_wp(contracts_to_update, blueprint_cache, all_expanded_contracts)
            logger.info(f"Completed batched updates for {len(contracts_to_update)} contracts")
            global contract_counter
            contract_counter += len(contracts_to_update)


async def update_contract_cache_only() -> None:
    """Standalone function to update the contract cache to reflect current EVE Online data.

    This function can be called independently to ensure the contract cache is always
    synchronized with real-world EVE Online contract changes, without performing
    any other contract processing tasks.

    Use this when you want to update the cache proactively or ensure it's current
    before running other operations.
    """
    logger.info("Updating contract cache to reflect current EVE Online data...")
    try:
        await fetch_and_expand_all_forge_contracts()
        logger.info("✓ Contract cache successfully updated to match EVE Online")
    except Exception as e:
        logger.error(f"✗ Failed to update contract cache: {e}")
        raise


async def get_user_contracts(char_id: int, access_token: str) -> List[Dict[str, Any]]:
    from datetime import datetime, timezone

    from esi_oauth import load_tokens, save_tokens

    # Get corporation contracts for the character
    try:
        # Get corporation ID
        from api_client import fetch_public_esi

        char_data = await fetch_public_esi(f"/characters/{char_id}/")
        if not char_data or "corporation_id" not in char_data:
            logger.warning("Could not get corporation ID")
            return []

        corp_id = char_data["corporation_id"]
        logger.info(f"Fetching corporation contracts for corp ID: {corp_id}")

        from contract_fetching import fetch_corporation_contracts

        corp_contracts = await fetch_corporation_contracts(corp_id, access_token)
        if not corp_contracts:
            logger.warning("No corporation contracts found")
            return []

        # Filter for outstanding item_exchange contracts
        outstanding_item_exchange = [
            c for c in corp_contracts if c.get("status") == "outstanding" and c.get("type") == "item_exchange"
        ]

        user_contracts = []

        for contract in outstanding_item_exchange:
            contract_id = contract["contract_id"]

            # Get contract items
            from contract_fetching import fetch_corporation_contract_items

            contract_items = await fetch_corporation_contract_items(corp_id, contract_id, access_token)

            if not contract_items:
                continue

            # Get item details
            items_details = []
            for item in contract_items:
                type_id = item.get("type_id")
                if type_id:
                    type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
                    item_name = type_data.get("name", f"Type {type_id}") if type_data else f"Type {type_id}"
                    items_details.append(
                        {
                            "type_id": type_id,
                            "name": item_name,
                            "quantity": item.get("quantity", 1),
                            "is_blueprint_copy": item.get("is_blueprint_copy", False),
                        }
                    )

            user_contract = {
                "contract_id": contract_id,
                "type": contract.get("type"),
                "price": contract.get("price", 0),
                "title": contract.get("title", ""),
                "items": items_details,
                "item_count": len(contract_items),
            }

            user_contracts.append(user_contract)

        logger.info(f"Found {len(user_contracts)} user outstanding contracts")
        return user_contracts

    except Exception as e:
        logger.error(f"Error fetching user contracts: {e}")
        return []


async def fetch_all_contract_items_for_contracts(contracts: List[Dict[str, Any]]) -> None:
    """Pre-fetch all contract items for the given contracts in parallel and store in cache.

    NOTE: This function is deprecated. Contract items are now assumed to be pre-cached
    in the all_contracts_forge.json file. No fetching is performed.
    """
    logger.info("Contract items are assumed to be pre-cached in all_contracts_forge.json - skipping fetch")
    return


async def main():
    """Main entry point for contract processing."""
    args = parse_arguments()

    # Load caches
    blueprint_cache = load_blueprint_cache()
    location_cache = load_location_cache()
    structure_cache = load_structure_cache()
    failed_structures = ContractCacheManager(CACHE_DIR).load_failed_structures()

    # Initialize WordPress post ID cache
    wp_post_id_cache = {}

    # Get tokens and process characters
    from esi_oauth import load_tokens

    tokens = load_tokens()

    if not tokens:
        logger.error("No tokens found. Please authenticate first.")
        return

    # Process each character's contracts
    for char_id_str, token_data in tokens.items():
        char_id = int(char_id_str)
        char_name = token_data.get("name", f"Character {char_id}")
        access_token = token_data.get("access_token")

        if not access_token:
            logger.warning(f"No access token for {char_name}, skipping")
            continue

        try:
            await process_character_contracts(
                char_id,
                access_token,
                char_name,
                wp_post_id_cache,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures,
            )
        except Exception as e:
            logger.error(f"Error processing contracts for {char_name}: {e}")
            continue

    logger.info(f"Contract processing complete. Processed {contract_counter} contracts total.")


if __name__ == "__main__":
    asyncio.run(main())
