"""
EVE Observer Contract Competition Analysis
Handles checking contract competition and outbid detection.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from api_client import fetch_public_contracts_async
from contract_fetching import get_issuer_names, get_region_from_location

logger = logging.getLogger(__name__)


async def check_contract_competition(
    contract_data: Dict[str, Any],
    contract_items: List[Dict[str, Any]],
    limit_to_issuer_ids: Optional[List[int]] = None,
    issuer_name_filter: Optional[str] = None,
    all_expanded_contracts: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, Optional[float]]:
    """Check if a sell contract has been outbid by cheaper competing contracts in the same region.

    Uses pre-expanded contract data when available, otherwise fetches contracts page by page.

    Args:
        contract_data: Contract information dictionary from ESI
        contract_items: List of items in the contract
        limit_to_issuer_ids: Optional list of issuer IDs to limit competition search to
        issuer_name_filter: Optional text to filter issuers by name (checks issuer name, corp name, and title)
        all_expanded_contracts: Optional list of pre-expanded contracts with full details

    Returns:
        Tuple of (is_outbid: bool, competing_price: float or None)
        - is_outbid: True if a cheaper competing contract exists
        - competing_price: The price per item of the cheapest competing contract, or None

    Note:
        Only checks single-item sell contracts (item_exchange type) with positive quantities.
        When all_expanded_contracts is provided, uses pre-fetched data for better performance.
    """
    if not contract_items or len(contract_items) != 1:
        return False, None  # Only check single item contracts

    contract_type = contract_data.get("type")
    if contract_type != "item_exchange":
        return False, None  # Only check sell orders

    item = contract_items[0]
    type_id = item.get("type_id")
    quantity = item.get("quantity", 1)
    is_blueprint_copy = item.get("is_blueprint_copy", False)
    contract_price = contract_data.get("price", 0)
    contract_id = contract_data.get("contract_id")
    contract_issuer_id = contract_data.get("issuer_id")

    if not type_id or quantity <= 0 or contract_price <= 0:
        return False, None

    price_per_item = contract_price / quantity

    # Get contract region
    region_id = await get_region_from_location(contract_data.get("start_location_id"))
    if not region_id:
        logger.warning(f"Could not determine region for contract {contract_id}")
        return False, None

    logger.info(
        f"Checking competition for contract {contract_id} (type_id: {type_id}, "
        f"price_per_item: {price_per_item:.2f}) in region {region_id}"
    )

    if limit_to_issuer_ids:
        logger.info(f"Limiting competition search to issuers: {limit_to_issuer_ids}")

    if issuer_name_filter:
        logger.info(f"Filtering issuers by name containing: '{issuer_name_filter}'")

    found_cheaper = False
    competing_price = None
    total_competing_found = 0

    if all_expanded_contracts is None:
        # Load expanded contracts from cache or fetch if needed
        logger.info("No expanded contracts provided, loading from cache...")
        from contract_expansion import fetch_and_expand_all_forge_contracts

        all_expanded_contracts = await fetch_and_expand_all_forge_contracts()

    if all_expanded_contracts and len(all_expanded_contracts) > 0:
        # Use pre-expanded contracts - much more efficient!
        logger.debug(f"Using pre-expanded contracts list with {len(all_expanded_contracts)} contracts")

        # Filter contracts for this region and basic criteria
        region_contracts = []
        for comp_contract in all_expanded_contracts:
            comp_start_location = comp_contract.get("start_location_id")
            if comp_start_location:
                comp_region_id = await get_region_from_location(comp_start_location)
                if comp_region_id == region_id:
                    region_contracts.append(comp_contract)

        logger.debug(f"Found {len(region_contracts)} contracts in region {region_id}")

        for comp_contract in region_contracts:
            comp_contract_id = comp_contract.get("contract_id")
            comp_price = comp_contract.get("price", 0)
            comp_issuer_id = comp_contract.get("issuer_id")
            comp_issuer_corp_id = comp_contract.get("issuer_corporation_id")
            comp_title = comp_contract.get("title", "")
            comp_items = comp_contract.get("items", [])

            # Debug: Log all contracts we're considering
            logger.debug(
                f"Evaluating contract {comp_contract_id}: type={comp_contract.get('type')}, status={comp_contract.get('status')}, price={comp_price}, issuer={comp_issuer_id}"
            )

            # Quick filters that don't require API calls
            if comp_contract.get("type") != "item_exchange":
                logger.debug(f"Skipping contract {comp_contract_id}: not item_exchange")
                continue
            if comp_contract.get("status") != "outstanding":
                logger.debug(f"Skipping contract {comp_contract_id}: not outstanding")
                continue
            if comp_contract.get("contract_id") == contract_id:
                logger.debug(f"Skipping contract {comp_contract_id}: same contract")
                continue
            if comp_contract.get("issuer_id") == contract_issuer_id:
                logger.debug(f"Skipping contract {comp_contract_id}: same issuer")
                continue

            # If limiting to specific issuers, check that here
            if limit_to_issuer_ids and comp_issuer_id not in limit_to_issuer_ids:
                logger.debug(
                    f"Skipping contract {comp_contract_id}: issuer {comp_issuer_id} not in allowed list {limit_to_issuer_ids}"
                )
                continue

            # If filtering by issuer name, check names here
            if issuer_name_filter:
                issuer_name = comp_contract.get("issuer_name", "")
                corp_name = comp_contract.get("issuer_corporation_name", "")

                # Check if any of the names contain the filter text (case insensitive)
                name_matches = (
                    issuer_name_filter.lower() in issuer_name.lower()
                    or issuer_name_filter.lower() in corp_name.lower()
                    or issuer_name_filter.lower() in comp_title.lower()
                )

                if not name_matches:
                    logger.debug(
                        f"Skipping contract {comp_contract_id}: name filter '{issuer_name_filter}' not found in '{issuer_name}'/'{corp_name}'/'{comp_title}'"
                    )
                    continue

                logger.debug(
                    f"Contract {comp_contract_id} matches name filter: issuer='{issuer_name}', corp='{corp_name}', title='{comp_title}'"
                )

            if comp_price <= 0:
                logger.debug(f"Skipping contract {comp_contract_id}: invalid price")
                continue

            # Use pre-expanded items data
            if not comp_items or len(comp_items) != 1:
                logger.debug(f"Skipping contract {comp_contract_id}: not single item or no items")
                continue

            comp_item = comp_items[0]
            comp_type_id = comp_item.get("type_id")
            comp_is_blueprint_copy = comp_item.get("is_blueprint_copy", False)
            comp_quantity = comp_item.get("quantity", 1)

            logger.debug(
                f"Contract {comp_contract_id} item: type_id={comp_type_id}, is_blueprint_copy={comp_is_blueprint_copy}, quantity={comp_quantity}"
            )

            if comp_type_id == type_id and comp_is_blueprint_copy == is_blueprint_copy:
                if comp_quantity > 0:
                    final_comp_price_per_item = comp_price / comp_quantity
                    total_competing_found += 1

                    logger.info(
                        f"Found competing contract {comp_contract_id}: price_per_item={final_comp_price_per_item:.2f}, our_price={price_per_item:.2f}"
                    )

                    if final_comp_price_per_item < price_per_item:
                        logger.info(
                            f"Contract {contract_id} outbid by contract {comp_contract_id} with "
                            f"price_per_item: {final_comp_price_per_item:.2f}"
                        )
                        found_cheaper = True
                        competing_price = final_comp_price_per_item
                        break  # Found cheaper contract, can stop
                else:
                    logger.debug(f"Skipping contract {comp_contract_id}: invalid quantity")
            else:
                logger.debug(
                    f"Skipping contract {comp_contract_id}: type_id mismatch ({comp_type_id} != {type_id}) or blueprint_copy mismatch ({comp_is_blueprint_copy} != {is_blueprint_copy})"
                )

    else:
        # Fallback to original page-by-page approach
        logger.debug("No pre-expanded contracts provided, using page-by-page fetching")

        # OPTIMIZED APPROACH: Check first few pages with smart filtering
        max_pages_to_check = 5  # Check up to 5 pages (5000 contracts max)

        for page in range(1, max_pages_to_check + 1):
            try:
                # Fetch contracts for this page, sorted by price (cheapest first)
                contracts_page = await fetch_public_contracts_async(region_id, page, sort_by_price=True)
                if not contracts_page:
                    logger.debug(f"No contracts found on page {page} for region {region_id}")
                    break

                logger.debug(f"Fetched {len(contracts_page)} contracts from page {page} in region {region_id}")

                # Define reasonable price range to check (70% to 200% of our contract price)
                min_price = price_per_item * 0.7
                max_price = price_per_item * 2.0

                # Process contracts with smart filtering
                for contract in contracts_page:
                    comp_contract_id = contract.get("contract_id")
                    comp_price = contract.get("price", 0)
                    comp_volume = contract.get("volume", 1)
                    comp_issuer_id = contract.get("issuer_id")
                    comp_issuer_corp_id = contract.get("issuer_corporation_id")
                    comp_title = contract.get("title", "")

                    # Debug: Log all contracts we're considering
                    logger.debug(
                        f"Evaluating contract {comp_contract_id}: type={contract.get('type')}, status={contract.get('status')}, price={comp_price}, issuer={comp_issuer_id}"
                    )

                    # Quick filters that don't require API calls
                    if contract.get("type") != "item_exchange":
                        logger.debug(f"Skipping contract {comp_contract_id}: not item_exchange")
                        continue
                    if contract.get("status") != "outstanding":
                        logger.debug(f"Skipping contract {comp_contract_id}: not outstanding")
                        continue
                    if contract.get("contract_id") == contract_id:
                        logger.debug(f"Skipping contract {comp_contract_id}: same contract")
                        continue
                    if contract.get("issuer_id") == contract_issuer_id:
                        logger.debug(f"Skipping contract {comp_contract_id}: same issuer")
                        continue

                    # If limiting to specific issuers, check that here
                    if limit_to_issuer_ids and comp_issuer_id not in limit_to_issuer_ids:
                        logger.debug(
                            f"Skipping contract {comp_contract_id}: issuer {comp_issuer_id} not in allowed list {limit_to_issuer_ids}"
                        )
                        continue

                    # If filtering by issuer name, check names here
                    if issuer_name_filter:
                        issuer_names = await get_issuer_names(
                            [comp_issuer_id, comp_issuer_corp_id] if comp_issuer_corp_id else [comp_issuer_id]
                        )
                        issuer_name = issuer_names.get(comp_issuer_id, "")
                        corp_name = issuer_names.get(comp_issuer_corp_id, "") if comp_issuer_corp_id else ""

                        # Check if any of the names contain the filter text (case insensitive)
                        name_matches = (
                            issuer_name_filter.lower() in issuer_name.lower()
                            or issuer_name_filter.lower() in corp_name.lower()
                            or issuer_name_filter.lower() in comp_title.lower()
                        )

                        if not name_matches:
                            logger.debug(
                                f"Skipping contract {comp_contract_id}: name filter '{issuer_name_filter}' not found in '{issuer_name}'/'{corp_name}'/'{comp_title}'"
                            )
                            continue

                        logger.debug(
                            f"Contract {comp_contract_id} matches name filter: issuer='{issuer_name}', corp='{corp_name}', title='{comp_title}'"
                        )

                    if comp_price <= 0:
                        logger.debug(f"Skipping contract {comp_contract_id}: invalid price")
                        continue

                    if comp_volume <= 0:
                        logger.debug(f"Skipping contract {comp_contract_id}: invalid volume")
                        continue

                    estimated_price_per_item = comp_price / comp_volume

                    # Skip if obviously not competitive
                    if estimated_price_per_item < min_price or estimated_price_per_item > max_price:
                        logger.debug(
                            f"Skipping contract {comp_contract_id}: price_per_item {estimated_price_per_item:.2f} outside range [{min_price:.2f}, {max_price:.2f}]"
                        )
                        continue

                    logger.debug(f"Contract {comp_contract_id} passed initial filters, fetching items...")

                    # Check if items are already cached in the contract data
                    comp_items = None
                    if all_expanded_contracts:
                        # Find this contract in the expanded contracts
                        for exp_contract in all_expanded_contracts:
                            if exp_contract.get("contract_id") == comp_contract_id:
                                comp_items = exp_contract.get("items", [])
                                break

                    if not comp_items:
                        logger.debug(f"Skipping contract {comp_contract_id}: no cached items available")
                        continue

                    if len(comp_items) != 1:
                        logger.debug(f"Skipping contract {comp_contract_id}: {len(comp_items)} items (not single item)")
                        continue

                    comp_item = comp_items[0]
                    comp_type_id = comp_item.get("type_id")
                    comp_is_blueprint_copy = comp_item.get("is_blueprint_copy", False)
                    comp_quantity = comp_item.get("quantity", 1)

                    logger.debug(
                        f"Contract {comp_contract_id} item: type_id={comp_type_id}, is_blueprint_copy={comp_is_blueprint_copy}, quantity={comp_quantity}"
                    )

                    if comp_type_id == type_id and comp_is_blueprint_copy == is_blueprint_copy:
                        if comp_quantity > 0:
                            final_comp_price_per_item = comp_price / comp_quantity
                            total_competing_found += 1

                            logger.info(
                                f"Found competing contract {comp_contract_id}: price_per_item={final_comp_price_per_item:.2f}, our_price={price_per_item:.2f}"
                            )

                            if final_comp_price_per_item < price_per_item:
                                logger.info(
                                    f"Contract {contract_id} outbid by contract {comp_contract_id} with "
                                    f"price_per_item: {final_comp_price_per_item:.2f}"
                                )
                                found_cheaper = True
                                competing_price = final_comp_price_per_item
                                break  # Found cheaper contract, can stop
                        else:
                            logger.debug(f"Skipping contract {comp_contract_id}: invalid quantity")
                    else:
                        logger.debug(
                            f"Skipping contract {comp_contract_id}: type_id mismatch ({comp_type_id} != {type_id}) or blueprint_copy mismatch ({comp_is_blueprint_copy} != {is_blueprint_copy})"
                        )

                if found_cheaper:
                    break  # Found cheaper contract, stop checking more pages

                # Check if there are more pages
                if len(contracts_page) < 1000:  # ESI returns max 1000 per page
                    break  # No more pages available

            except Exception as e:
                logger.error(f"Error fetching page {page} for region {region_id}: {e}")
                break

    if found_cheaper:
        return True, competing_price

    logger.info(
        f"No competing contracts found for contract {contract_id} (checked {total_competing_found} potential competitors)"
    )
    return False, None


async def check_contract_competition_hybrid(
    contract_data: Dict[str, Any],
    contract_items: List[Dict[str, Any]],
    limit_to_issuer_ids: Optional[List[int]] = None,
    issuer_name_filter: Optional[str] = None,
    all_expanded_contracts: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, Optional[float], Optional[Dict[str, float]]]:
    """Check if a sell contract has been outbid by cheaper competing contracts in the same region.

    This is a wrapper around check_contract_competition that maintains the same interface
    for backward compatibility, but only performs contract-to-contract comparison.

    Args:
        contract_data: Contract information dictionary from ESI
        contract_items: List of items in the contract
        limit_to_issuer_ids: Optional list of issuer IDs to limit competition search to
        issuer_name_filter: Optional text to filter issuers by name (checks issuer name, corp name, and title)
        all_expanded_contracts: Optional list of pre-expanded contracts with full details

    Returns:
        Tuple of (is_outbid: bool, competing_price: float or None, market_data: None)
        - is_outbid: True if a cheaper competing contract exists
        - competing_price: The price per item of the cheapest competing contract, or None
        - market_data: Always None (no market data returned)

    Note:
        Only checks single-item sell contracts (item_exchange type) with positive quantities.
    """
    # Only perform contract-to-contract comparison
    is_outbid, competing_price = await check_contract_competition(
        contract_data, contract_items, limit_to_issuer_ids, issuer_name_filter, all_expanded_contracts
    )
    return is_outbid, competing_price, None


async def check_contracts_competition_concurrent(
    contract_data_list: List[Dict[str, Any]],
    contract_items_list: List[List[Dict[str, Any]]],
    all_expanded_contracts: Optional[List[Dict[str, Any]]] = None,
) -> List[Tuple[bool, Optional[float]]]:
    """Check competition for multiple contracts concurrently.

    Args:
        contract_data_list: List of contract information dictionaries
        contract_items_list: List of contract items lists (corresponding to contract_data_list)
        all_expanded_contracts: Optional list of pre-expanded contracts for competition analysis

    Returns:
        List of tuples (is_outbid, competing_price) for each contract
    """
    if len(contract_data_list) != len(contract_items_list):
        raise ValueError("contract_data_list and contract_items_list must have the same length")

    # Create tasks for concurrent execution
    tasks = [
        check_contract_competition(contract_data, contract_items, all_expanded_contracts=all_expanded_contracts)
        for contract_data, contract_items in zip(contract_data_list, contract_items_list)
    ]

    # Execute all competition checks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions that occurred
    processed_results: List[Tuple[bool, Optional[float]]] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                f"Error checking competition for contract {contract_data_list[i].get('contract_id')}: {result}"
            )
            processed_results.append((False, None))  # Default to not outbid on error
        else:
            # Type narrowing: result is Tuple[bool, Optional[float]] when not an exception
            processed_results.append(result)  # type: ignore

    return processed_results
