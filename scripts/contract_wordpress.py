"""
EVE Observer Contract WordPress Integration
Handles updating contracts in WordPress.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api_client import fetch_type_icon, validate_input_params, wp_request
from blueprint_processor import update_blueprint_from_asset_in_wp
from cache_manager import load_blueprint_cache, load_blueprint_type_cache
from config import WORDPRESS_BATCH_SIZE
from contract_fetching import fetch_character_contract_items, fetch_corporation_contract_items

logger = logging.getLogger(__name__)


@validate_input_params(dict, bool, (int, type(None)), (str, type(None)), (dict, type(None)), (list, type(None)))
async def generate_contract_title(
    contract_data: Dict[str, Any],
    for_corp: bool = False,
    entity_id: Optional[int] = None,
    contract_items: Optional[List[Dict[str, Any]]] = None,
    blueprint_cache: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a descriptive contract title based on contract type and items.

    Creates human-readable titles that include item names, quantities, and contract details.
    Special handling for blueprint contracts and mixed item types.

    Args:
        contract_data: Contract information dictionary from ESI
        for_corp: Whether this is a corporation contract (affects title prefix)
        entity_id: Character or corporation ID (for context)
        contract_items: List of items in the contract (optional)
        blueprint_cache: Cached blueprint names (loaded automatically if not provided)

    Returns:
        Formatted contract title string

    Note:
        Titles follow the format: "[Corp] Item Name - Contract ID" for blueprints,
        or "[Corp] X Items (xQuantity) - Contract ID" for regular items.
    """
    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()

    blueprint_type_cache = load_blueprint_type_cache()

    contract_id = contract_data.get("contract_id")
    contract_type = contract_data.get("type", "unknown")
    status = contract_data.get("status", "unknown").title()

    # If no items, use default format
    if not contract_items:
        type_names = {"item_exchange": "Item Exchange", "auction": "Auction", "courier": "Courier", "loan": "Loan"}
        type_name = type_names.get(contract_type, contract_type.title())
        title = f"Contract {contract_id} - {type_name} ({status})"
    else:
        # If we have items, create a more descriptive title
        if len(contract_items) == 1:
            # Single item contract
            item = contract_items[0]
            type_id = item.get("type_id")
            quantity = item.get("quantity", 1)

            if type_id:
                # Get item name
                item_name = load_blueprint_cache().get(str(type_id))
                if item_name is None:
                    from api_client import fetch_public_esi

                    type_data = await fetch_public_esi(f"/universe/types/{type_id}")
                    if type_data:
                        item_name = type_data.get("name", f"Item {type_id}")
                        # Only cache if it's actually a blueprint
                        if "Blueprint" in item_name:
                            cleaned_name = item_name.replace(" Blueprint", "").strip()
                            blueprint_cache[str(type_id)] = cleaned_name
                            from cache_manager import save_blueprint_cache

                            save_blueprint_cache(blueprint_cache)
                    else:
                        item_name = f"Item {type_id}"

                # Check if it's a blueprint (quantity -1 indicates BPO, or check if it's in blueprint cache)
                is_blueprint = str(type_id) in blueprint_type_cache and blueprint_type_cache[str(type_id)]
                if not is_blueprint:
                    # Double-check with ESI
                    from api_client import fetch_public_esi

                    type_data = await fetch_public_esi(f"/universe/types/{type_id}")
                    is_blueprint = type_data and "Blueprint" in type_data.get("name", "")

                if is_blueprint:
                    title = f"{item_name} - Contract {contract_id}"
                else:
                    # Regular item
                    title = f"{item_name} (x{quantity}) - Contract {contract_id}"

        else:
            # Multiple items contract - count blueprints and total quantity in single pass
            blueprint_count = 0
            total_quantity = 0

            for item in contract_items:
                quantity = item.get("quantity", 1)
                total_quantity += abs(quantity)  # Use abs in case of BPOs

                # Check if it's a blueprint
                type_id = item.get("type_id")
                if type_id:
                    # First check if it's in blueprint cache
                    if str(type_id) in blueprint_type_cache and blueprint_type_cache[str(type_id)]:
                        blueprint_count += 1
                    else:
                        # Check with ESI
                        from api_client import fetch_public_esi

                        type_data = await fetch_public_esi(f"/universe/types/{type_id}")
                        if type_data and "Blueprint" in type_data.get("name", ""):
                            blueprint_count += 1

            if blueprint_count == len(contract_items):
                # All items are blueprints
                title = f"{blueprint_count} Blueprints - Contract {contract_id}"
            elif blueprint_count > 0:
                # Mix of blueprints and other items
                title = (
                    f"{blueprint_count} Blueprints + "
                    f"{len(contract_items) - blueprint_count} Items - Contract {contract_id}"
                )
            else:
                # No blueprints, just regular items
                title = f"{len(contract_items)} Items (x{total_quantity}) - Contract {contract_id}"

    if for_corp:
        title = f"[Corp] {title}"

    return title


@validate_input_params(int, dict, bool, (int, type(None)), (str, type(None)), (dict, type(None)), (list, type(None)))
async def update_contract_in_wp(
    contract_id: int,
    contract_data: Dict[str, Any],
    for_corp: bool = False,
    entity_id: Optional[int] = None,
    access_token: Optional[str] = None,
    blueprint_cache: Optional[Dict[str, Any]] = None,
    all_expanded_contracts: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Update or create a contract post in WordPress with comprehensive metadata.

    Creates or updates WordPress posts for EVE contracts, including market competition
    analysis for sell orders. Only processes contracts containing blueprints.

    Args:
        contract_id: The EVE contract ID
        contract_data: Contract information dictionary from ESI
        for_corp: Whether this is a corporation contract
        entity_id: Character or corporation ID that has access to the contract
        access_token: Valid ESI access token for fetching contract items
        blueprint_cache: Cached blueprint names (loaded automatically if not provided)
        all_expanded_contracts: Optional list of pre-expanded contracts for competition analysis

    Returns:
        None

    Note:
        - Only creates posts for contracts containing blueprints
        - Performs market competition analysis for outstanding sell contracts
        - Updates existing posts only if data has changed
        - Includes contract items, pricing, and location metadata
    """
    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()

    blueprint_type_cache = load_blueprint_type_cache()

    slug = f"contract-{contract_id}"
    # Check if post exists by slug
    existing_posts = await wp_request("GET", f"/wp/v2/eve_contract?slug={slug}")
    existing_post = existing_posts[0] if existing_posts else None

    # Fetch contract items if we have access token
    contract_items = None
    if access_token:
        # First try to get items from the expanded contracts cache
        if all_expanded_contracts:
            for expanded_contract in all_expanded_contracts:
                if expanded_contract.get("contract_id") == contract_id:
                    contract_items = expanded_contract.get("items", [])
                    logger.debug(f"Using cached items for contract {contract_id}: {len(contract_items)} items")
                    break

        # If not found in cache, fetch individually (fallback)
        if contract_items is None:
            if for_corp and entity_id:
                contract_items = await fetch_corporation_contract_items(entity_id, contract_id, access_token)
            elif not for_corp and entity_id:
                contract_items = await fetch_character_contract_items(entity_id, contract_id, access_token)

    # Get region ID from start location
    from contract_fetching import get_region_from_location

    region_id = None
    start_location_id = contract_data.get("start_location_id")
    if start_location_id:
        region_id = await get_region_from_location(start_location_id)

    # Check if contract contains blueprints - only track contracts with blueprints
    has_blueprint = False
    if contract_items:
        for item in contract_items:
            type_id = item.get("type_id")
            if type_id and str(type_id) in blueprint_type_cache and blueprint_type_cache[str(type_id)]:
                has_blueprint = True
                break

    if not has_blueprint:
        logger.info(f"Contract {contract_id} contains no blueprints, skipping")
        return

    title = await generate_contract_title(
        contract_data,
        for_corp=for_corp,
        entity_id=entity_id,
        contract_items=contract_items,
        blueprint_cache=blueprint_cache,
    )

    post_data = {
        "title": title,
        "slug": slug,
        "status": "publish",
        "meta": {
            "_eve_contract_id": str(contract_id),
            "_eve_contract_type": contract_data.get("type"),
            "_eve_contract_status": contract_data.get("status"),
            "_eve_contract_issuer_id": str(contract_data.get("issuer_id"))
            if contract_data.get("issuer_id") is not None
            else None,
            "_eve_contract_issuer_corp_id": str(contract_data.get("issuer_corporation_id"))
            if contract_data.get("issuer_corporation_id") is not None
            else None,
            "_eve_contract_assignee_id": str(contract_data.get("assignee_id"))
            if contract_data.get("assignee_id")
            else None,
            "_eve_contract_acceptor_id": str(contract_data.get("acceptor_id"))
            if contract_data.get("acceptor_id")
            else None,
            "_eve_contract_start_location_id": str(contract_data.get("start_location_id"))
            if contract_data.get("start_location_id")
            else None,
            "_eve_contract_end_location_id": str(contract_data.get("end_location_id"))
            if contract_data.get("end_location_id")
            else None,
            "_eve_contract_region_id": str(region_id) if region_id else None,
            "_eve_contract_date_issued": contract_data.get("date_issued"),
            "_eve_contract_date_expired": contract_data.get("date_expired"),
            "_eve_contract_date_accepted": contract_data.get("date_accepted"),
            "_eve_contract_date_completed": contract_data.get("date_completed"),
            "_eve_contract_price": str(contract_data.get("price")) if contract_data.get("price") is not None else None,
            "_eve_contract_reward": str(contract_data.get("reward"))
            if contract_data.get("reward") is not None
            else None,
            "_eve_contract_collateral": str(contract_data.get("collateral"))
            if contract_data.get("collateral") is not None
            else None,
            "_eve_contract_buyout": str(contract_data.get("buyout"))
            if contract_data.get("buyout") is not None
            else None,
            "_eve_contract_volume": str(contract_data.get("volume"))
            if contract_data.get("volume") is not None
            else None,
            "_eve_contract_days_to_complete": str(contract_data.get("days_to_complete"))
            if contract_data.get("days_to_complete") is not None
            else None,
            "_eve_contract_title": contract_data.get("title"),
            "_eve_contract_for_corp": str(for_corp).lower(),
            "_eve_contract_entity_id": str(entity_id),
            "_eve_last_updated": datetime.now(timezone.utc).isoformat(),
        },
    }

    # Remove null values from meta to avoid WordPress validation errors
    post_data["meta"] = {k: v for k, v in post_data["meta"].items() if v is not None}

    # Add items data if available
    if contract_items:
        post_data["meta"]["_eve_contract_items"] = json.dumps(contract_items)

        # Store item types for easier querying
        item_types = [str(item.get("type_id")) for item in contract_items if item.get("type_id")]
        post_data["meta"]["_eve_contract_item_types"] = ",".join(item_types)

        # Check for market competition on outstanding sell contracts
        from contract_competition import check_contract_competition

        if contract_data.get("status") == "outstanding" and contract_data.get("type") == "item_exchange":
            is_outbid, competing_price = await check_contract_competition(
                contract_data, contract_items, all_expanded_contracts=all_expanded_contracts
            )
            if is_outbid:
                post_data["meta"]["_eve_contract_outbid"] = "1"
                post_data["meta"]["_eve_contract_competing_price"] = str(competing_price)
                logger.warning(f"Contract {contract_id} is outbid by contract price: {competing_price}")
            else:
                post_data["meta"]["_eve_contract_outbid"] = "0"
                if "_eve_contract_competing_price" in post_data["meta"]:
                    del post_data["meta"]["_eve_contract_competing_price"]
        else:
            # Not a sell contract or not outstanding - ensure outbid is false
            post_data["meta"]["_eve_contract_outbid"] = "0"
            if "_eve_contract_competing_price" in post_data["meta"]:
                del post_data["meta"]["_eve_contract_competing_price"]
    else:
        # No contract items - ensure outbid is set to false
        post_data["meta"]["_eve_contract_outbid"] = "0"
        if "_eve_contract_competing_price" in post_data["meta"]:
            del post_data["meta"]["_eve_contract_competing_price"]

    if existing_post:
        existing_meta = existing_post.get("meta", {})
        # Send alert if this is newly outbid
        was_outbid = existing_meta.get("_eve_contract_outbid") == "1"
        if not was_outbid and post_data["meta"].get("_eve_contract_outbid") == "1":
            price = post_data["meta"].get("_eve_contract_competing_price", "unknown")
            logger.warning(f"Contract {contract_id} is newly outbid by contract price: {price}")
        # Check if title changed before updating
        existing_title = existing_post.get("title", {}).get("rendered", "")

        # Compare key fields to see if update is needed
        needs_update = (
            existing_title != title
            or str(existing_meta.get("_eve_contract_status", "")) != str(contract_data.get("status", ""))
            or str(existing_meta.get("_eve_contract_items", ""))
            != str(json.dumps(contract_items) if contract_items else "")
            or str(existing_meta.get("_eve_contract_outbid", "0"))
            != str(post_data["meta"].get("_eve_contract_outbid", "0"))
        )

        if not needs_update:
            logger.info(f"Contract {contract_id} unchanged, skipping update")
            return

        # Update existing
        post_id = existing_post["id"]
        result = await wp_request("PUT", f"/wp/v2/eve_contract/{post_id}", post_data)
    else:
        # Create new (without region_id to avoid ACF protection issues)
        # Add thumbnail from first contract item
        if contract_items and len(contract_items) > 0:
            first_item_type_id = contract_items[0].get("type_id")
            if first_item_type_id:
                image_url = await fetch_type_icon(first_item_type_id, size=512)
                post_data["meta"]["_thumbnail_external_url"] = image_url
        result = await wp_request("POST", "/wp/v2/eve_contract", post_data)

    if result:
        logger.info(f"Updated contract: {contract_id} - {title}")
    else:
        logger.error(f"Failed to update contract {contract_id}")


@validate_input_params(
    int,
    dict,
    bool,
    (float, type(None)),
    bool,
    (int, type(None)),
    (str, type(None)),
    (dict, type(None)),
    (list, type(None)),
)
async def update_contract_in_wp_with_competition_result(
    contract_id: int,
    contract_data: Dict[str, Any],
    is_outbid: bool,
    competing_price: Optional[float],
    for_corp: bool = False,
    entity_id: Optional[int] = None,
    access_token: Optional[str] = None,
    blueprint_cache: Optional[Dict[str, Any]] = None,
    all_expanded_contracts: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Update or create a contract post in WordPress with pre-calculated competition result.

    Similar to update_contract_in_wp but takes competition result as parameters
    instead of calculating it internally.

    Args:
        contract_id: The EVE contract ID
        contract_data: Contract information dictionary from ESI
        is_outbid: Whether this contract has been outbid
        competing_price: The competing price if outbid, None otherwise
        for_corp: Whether this is a corporation contract
        entity_id: Character or corporation ID that has access to the contract
        access_token: Valid ESI access token for fetching contract items
        blueprint_cache: Cached blueprint names (loaded automatically if not provided)
        all_expanded_contracts: Optional list of pre-expanded contracts for competition analysis

    Returns:
        None
    """
    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()

    blueprint_type_cache = load_blueprint_type_cache()

    slug = f"contract-{contract_id}"
    # Check if post exists by slug
    existing_posts = await wp_request("GET", f"/wp/v2/eve_contract?slug={slug}")
    existing_post = existing_posts[0] if existing_posts else None

    # Fetch contract items if we have access token
    contract_items = None
    if access_token:
        # First try to get items from the expanded contracts cache
        if all_expanded_contracts:
            for expanded_contract in all_expanded_contracts:
                if expanded_contract.get("contract_id") == contract_id:
                    contract_items = expanded_contract.get("items", [])
                    logger.debug(f"Using cached items for contract {contract_id}: {len(contract_items)} items")
                    break

        # If not found in cache, fetch individually (fallback)
        if contract_items is None:
            if for_corp and entity_id:
                contract_items = await fetch_corporation_contract_items(entity_id, contract_id, access_token)
            elif not for_corp and entity_id:
                contract_items = await fetch_character_contract_items(entity_id, contract_id, access_token)

    # Get region ID from start location
    from contract_fetching import get_region_from_location

    region_id = None
    start_location_id = contract_data.get("start_location_id")
    if start_location_id:
        region_id = await get_region_from_location(start_location_id)

    # Check if contract contains blueprints - only track contracts with blueprints
    has_blueprint = False
    if contract_items:
        for item in contract_items:
            type_id = item.get("type_id")
            if type_id and str(type_id) in blueprint_type_cache and blueprint_type_cache[str(type_id)]:
                has_blueprint = True
                break

    if not has_blueprint:
        logger.info(f"Contract {contract_id} contains no blueprints, skipping")
        return

    title = await generate_contract_title(
        contract_data,
        for_corp=for_corp,
        entity_id=entity_id,
        contract_items=contract_items,
        blueprint_cache=blueprint_cache,
    )

    post_data = {
        "title": title,
        "slug": slug,
        "status": "publish",
        "meta": {
            "_eve_contract_id": str(contract_id),
            "_eve_contract_type": contract_data.get("type"),
            "_eve_contract_status": contract_data.get("status"),
            "_eve_contract_issuer_id": str(contract_data.get("issuer_id"))
            if contract_data.get("issuer_id") is not None
            else None,
            "_eve_contract_issuer_corp_id": str(contract_data.get("issuer_corporation_id"))
            if contract_data.get("issuer_corporation_id") is not None
            else None,
            "_eve_contract_assignee_id": str(contract_data.get("assignee_id"))
            if contract_data.get("assignee_id")
            else None,
            "_eve_contract_acceptor_id": str(contract_data.get("acceptor_id"))
            if contract_data.get("acceptor_id")
            else None,
            "_eve_contract_start_location_id": str(contract_data.get("start_location_id"))
            if contract_data.get("start_location_id")
            else None,
            "_eve_contract_end_location_id": str(contract_data.get("end_location_id"))
            if contract_data.get("end_location_id")
            else None,
            "_eve_contract_region_id": str(region_id) if region_id else None,
            "_eve_contract_date_issued": contract_data.get("date_issued"),
            "_eve_contract_date_expired": contract_data.get("date_expired"),
            "_eve_contract_date_accepted": contract_data.get("date_accepted"),
            "_eve_contract_date_completed": contract_data.get("date_completed"),
            "_eve_contract_price": str(contract_data.get("price")) if contract_data.get("price") is not None else None,
            "_eve_contract_reward": str(contract_data.get("reward"))
            if contract_data.get("reward") is not None
            else None,
            "_eve_contract_collateral": str(contract_data.get("collateral"))
            if contract_data.get("collateral") is not None
            else None,
            "_eve_contract_buyout": str(contract_data.get("buyout"))
            if contract_data.get("buyout") is not None
            else None,
            "_eve_contract_volume": str(contract_data.get("volume"))
            if contract_data.get("volume") is not None
            else None,
            "_eve_contract_days_to_complete": str(contract_data.get("days_to_complete"))
            if contract_data.get("days_to_complete") is not None
            else None,
            "_eve_contract_title": contract_data.get("title"),
            "_eve_contract_for_corp": str(for_corp).lower(),
            "_eve_contract_entity_id": str(entity_id),
            "_eve_last_updated": datetime.now(timezone.utc).isoformat(),
        },
    }

    # Remove null values from meta to avoid WordPress validation errors
    post_data["meta"] = {k: v for k, v in post_data["meta"].items() if v is not None}

    # Add items data if available
    if contract_items:
        post_data["meta"]["_eve_contract_items"] = json.dumps(contract_items)

        # Store item types for easier querying
        item_types = [str(item.get("type_id")) for item in contract_items if item.get("type_id")]
        post_data["meta"]["_eve_contract_item_types"] = ",".join(item_types)

        # Use pre-calculated competition result
        if is_outbid:
            post_data["meta"]["_eve_contract_outbid"] = "1"
            post_data["meta"]["_eve_contract_competing_price"] = str(competing_price)
            logger.warning(f"Contract {contract_id} is outbid by contract price: {competing_price}")
        else:
            post_data["meta"]["_eve_contract_outbid"] = "0"
            if "_eve_contract_competing_price" in post_data["meta"]:
                del post_data["meta"]["_eve_contract_competing_price"]
    else:
        # No contract items - ensure outbid is set to false
        post_data["meta"]["_eve_contract_outbid"] = "0"
        if "_eve_contract_competing_price" in post_data["meta"]:
            del post_data["meta"]["_eve_contract_competing_price"]

    if existing_post:
        existing_meta = existing_post.get("meta", {})
        # Send alert if this is newly outbid
        was_outbid = existing_meta.get("_eve_contract_outbid") == "1"
        if not was_outbid and post_data["meta"].get("_eve_contract_outbid") == "1":
            price = post_data["meta"].get("_eve_contract_competing_price", "unknown")
            logger.warning(f"Contract {contract_id} is newly outbid by contract price: {price}")
        # Check if title changed before updating
        existing_title = existing_post.get("title", {}).get("rendered", "")

        # Compare key fields to see if update is needed
        needs_update = (
            existing_title != title
            or str(existing_meta.get("_eve_contract_status", "")) != str(contract_data.get("status", ""))
            or str(existing_meta.get("_eve_contract_items", ""))
            != str(json.dumps(contract_items) if contract_items else "")
            or str(existing_meta.get("_eve_contract_outbid", "0"))
            != str(post_data["meta"].get("_eve_contract_outbid", "0"))
        )

        if not needs_update:
            logger.info(f"Contract {contract_id} unchanged, skipping update")
            return

        # Update existing
        post_id = existing_post["id"]
        result = await wp_request("PUT", f"/wp/v2/eve_contract/{post_id}", post_data)
    else:
        # Create new (without region_id to avoid ACF protection issues)
        # Add thumbnail from first contract item
        if contract_items and len(contract_items) > 0:
            first_item_type_id = contract_items[0].get("type_id")
            if first_item_type_id:
                image_url = await fetch_type_icon(first_item_type_id, size=512)
                post_data["meta"]["_thumbnail_external_url"] = image_url
        result = await wp_request("POST", "/wp/v2/eve_contract", post_data)

    if result:
        logger.info(f"Updated contract: {contract_id} - {title}")
    else:
        logger.error(f"Failed to update contract {contract_id}")


@validate_input_params(list)
async def batch_update_contracts_in_wp(
    contract_updates: List[Dict[str, Any]],
    blueprint_cache: Optional[Dict[str, Any]] = None,
    all_expanded_contracts: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Batch update multiple contracts in WordPress to reduce API calls.

    Args:
        contract_updates: List of contract update dictionaries with keys:
            - contract_id: EVE contract ID
            - contract_data: Contract information dictionary from ESI
            - is_outbid: Whether this contract has been outbid
            - competing_price: The competing price if outbid, None otherwise
            - for_corp: Whether this is a corporation contract
            - entity_id: Character or corporation ID that has access to the contract
            - access_token: Valid ESI access token for fetching contract items
        blueprint_cache: Cached blueprint names (loaded automatically if not provided)
        all_expanded_contracts: Optional list of pre-expanded contracts for competition analysis
    """
    if not contract_updates:
        logger.info("No contract updates to process")
        return

    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()

    logger.info(f"Batch updating {len(contract_updates)} contracts in WordPress...")

    # Process contracts in batches to avoid overwhelming WordPress
    batch_size = WORDPRESS_BATCH_SIZE  # Configurable batch size for WordPress updates
    total_processed = 0

    for i in range(0, len(contract_updates), batch_size):
        batch = contract_updates[i : i + batch_size]
        logger.info(
            f"Processing batch {i//batch_size + 1}/{(len(contract_updates) + batch_size - 1)//batch_size} "
            f"({len(batch)} contracts)"
        )

        # Create tasks for concurrent processing within the batch
        update_tasks = []
        for update_info in batch:
            task = update_contract_in_wp_with_competition_result(
                update_info["contract"]["contract_id"],
                update_info["contract"],
                update_info["is_outbid"],
                update_info["competing_price"],
                update_info["for_corp"],
                update_info["entity_id"],
                update_info["access_token"],
                blueprint_cache,
                all_expanded_contracts,
            )
            update_tasks.append(task)

        # Execute batch concurrently
        await asyncio.gather(*update_tasks, return_exceptions=True)
        total_processed += len(batch)

        # Small delay between batches to be respectful to WordPress
        if i + batch_size < len(contract_updates):
            await asyncio.sleep(0.5)

    logger.info(f"Completed batch update of {total_processed} contracts")


@validate_input_params(set, set)
async def cleanup_contract_posts(allowed_corp_ids: set, allowed_issuer_ids: set) -> None:
    """
    Clean up contract posts that don't match filtering criteria.

    Removes contract posts from unauthorized issuers or with finished/deleted status.
    Lists expired contracts for manual deletion to preserve private contract visibility.

    Args:
        allowed_corp_ids: Set of corporation IDs allowed for contract processing.
        allowed_issuer_ids: Set of character IDs allowed as contract issuers.

    Note:
        Preserves private contracts that may still be visible to authorized characters.
        Only removes contracts from unauthorized sources or completed contracts.
    """
    logger.info("Cleaning up contract posts...")

    contracts = await wp_request("GET", "/wp/v2/eve_contract", {"per_page": 100})
    if contracts:
        for contract in contracts:
            meta = contract.get("meta", {})
            status = meta.get("_eve_contract_status")
            issuer_corp_id = meta.get("_eve_contract_issuer_corp_id")
            issuer_id = meta.get("_eve_contract_issuer_id")
            contract_id = meta.get("_eve_contract_id")

            should_delete = False
            # Don't delete private contracts - they may still be visible to authorized characters
            # Only delete contracts from unauthorized issuers or finished/deleted contracts
            if status in ["finished", "deleted"]:
                should_delete = True
                logger.info(f"Deleting {status} contract: {contract_id}")
            elif (
                issuer_corp_id
                and int(issuer_corp_id) not in allowed_corp_ids
                and issuer_id
                and int(issuer_id) not in allowed_issuer_ids
            ):
                should_delete = True
                logger.info(f"Deleting contract from unauthorized issuer: {contract_id}")
            elif status == "expired":
                # List expired contracts for manual deletion
                title = contract.get("title", {}).get("rendered", f"Contract {contract_id}")
                logger.info(f"EXPIRED CONTRACT TO DELETE MANUALLY: {title} (ID: {contract_id})")

            if should_delete:
                result = await wp_request("DELETE", f"/wp/v2/eve_contract/{contract['id']}", {"force": True})
                if result:
                    logger.info(f"Deleted contract: {contract_id}")
                else:
                    logger.error(f"Failed to delete contract: {contract_id}")
