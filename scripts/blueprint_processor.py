#!/usr/bin/env python3
"""
EVE Observer Blueprint Processor
Handles fetching and processing of EVE blueprint data.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from api_client import delete_wp_post, fetch_esi, fetch_public_esi, fetch_type_icon
from cache_manager import (
    get_cached_wp_post_id,
    load_blueprint_cache,
    load_blueprint_type_cache,
    load_failed_structures,
    load_location_cache,
    load_structure_cache,
    load_wp_post_id_cache,
    save_blueprint_cache,
    save_blueprint_type_cache,
    save_failed_structures,
    save_location_cache,
    save_structure_cache,
    set_cached_wp_post_id,
)
from config import WP_BASE_URL, WP_PER_PAGE
from data_processors import get_wp_auth

logger = logging.getLogger(__name__)


async def update_blueprint_in_wp(
    blueprint_data: Dict[str, Any],
    wp_post_id_cache: Dict[str, Any],
    char_id: int,
    access_token: str,
    blueprint_cache: Optional[Dict[str, Any]] = None,
    location_cache: Optional[Dict[str, Any]] = None,
    structure_cache: Optional[Dict[str, Any]] = None,
    failed_structures: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Update or create a blueprint post in WordPress from direct blueprint endpoint data.

    Processes blueprint information including ME/TE levels, location, and type details.
    Only tracks BPOs (quantity == -1), skipping BPCs. Caches location and type data
    for performance.

    Args:
        blueprint_data: Blueprint data from ESI API.
        wp_post_id_cache: Cache of WordPress post IDs.
        char_id: Character ID for auth.
        access_token: Valid OAuth access token.
        blueprint_cache: Optional cache for blueprint names.
        location_cache: Optional cache for location names.
        structure_cache: Optional cache for structure names.
        failed_structures: Optional cache for failed structure fetches.

    Returns:
        None

    Raises:
        No explicit raises; logs errors internally.
    """
    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()
    if location_cache is None:
        location_cache = load_location_cache()
    if structure_cache is None:
        structure_cache = load_structure_cache()
    if failed_structures is None:
        failed_structures = load_failed_structures()
    if wp_post_id_cache is None:
        wp_post_id_cache = load_wp_post_id_cache()

    item_id = blueprint_data.get("item_id")
    if not item_id:
        logger.error(f"Blueprint data missing item_id: {blueprint_data}")
        return

    # Skip BPCs - only track BPOs
    quantity = blueprint_data.get("quantity", -1)
    if quantity != -1:
        logger.info(f"Skipping BPC (quantity={quantity}) for item_id: {item_id}")
        return

    slug = f"blueprint-{item_id}"

    # Try to get post ID from cache first
    cached_post_id = get_cached_wp_post_id(wp_post_id_cache, "eve_blueprint", item_id)

    if cached_post_id:
        # Use direct post ID lookup
        response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{cached_post_id}", auth=get_wp_auth())
        if response.status_code == 200:
            existing_post = response.json()
        else:
            # Cache might be stale, fall back to slug lookup
            cached_post_id = None
            existing_post = None
    else:
        # Fall back to slug lookup
        response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint?slug={slug}", auth=get_wp_auth())
        existing_posts = response.json() if response.status_code == 200 else []
        existing_post = existing_posts[0] if existing_posts else None

        # Cache the post ID if found
        if existing_post:
            set_cached_wp_post_id(wp_post_id_cache, "eve_blueprint", item_id, existing_post["id"])

    # Get blueprint name and details
    type_id = blueprint_data.get("type_id")
    me = blueprint_data.get("material_efficiency", 0)
    te = blueprint_data.get("time_efficiency", 0)
    location_id = blueprint_data.get("location_id")
    quantity = blueprint_data.get("quantity", -1)

    # Get blueprint name from cache or API
    if type_id:
        if str(type_id) in blueprint_cache:
            type_name = blueprint_cache[str(type_id)]
        else:
            type_data = await fetch_public_esi(f"/universe/types/{type_id}")
            if type_data:
                type_name = type_data.get("name", f"Blueprint {item_id}").replace(" Blueprint", "").strip()
                blueprint_cache[str(type_id)] = type_name
                save_blueprint_cache(blueprint_cache)
            else:
                type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()
    else:
        type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()

    # Determine BPO or BPC
    bp_type = "BPO" if quantity == -1 else "BPC"

    # Get location name from cache or API
    if location_id:
        location_id_str = str(location_id)
        if location_id_str in location_cache:
            location_name = location_cache[location_id_str]
        elif location_id >= 1000000000000:  # Structures (citadels, etc.)
            if location_id_str in failed_structures:
                location_name = f"Citadel {location_id}"
            elif location_id_str in structure_cache:
                location_name = structure_cache[location_id_str]
            else:
                # Try auth fetch for private structures
                struct_data = await fetch_esi(f"/universe/structures/{location_id}", char_id, access_token)
                if struct_data:
                    location_name = struct_data.get("name", f"Citadel {location_id}")
                    structure_cache[location_id_str] = location_name
                    save_structure_cache(structure_cache)
                else:
                    location_name = f"Citadel {location_id}"
                    failed_structures[location_id_str] = True
                    save_failed_structures(failed_structures)
        else:  # Stations - public
            if location_id_str in location_cache:
                location_name = location_cache[location_id_str]
            else:
                loc_data = await fetch_public_esi(f"/universe/stations/{location_id}")
                location_name = loc_data.get("name", f"Station {location_id}") if loc_data else f"Station {location_id}"
                location_cache[location_id_str] = location_name
                save_location_cache(location_cache)
    else:
        location_name = "Unknown Location"

    # Construct title
    title = f"{type_name} {bp_type} {me}/{te} ({location_name}) – ID: {item_id}"

    post_data = {
        "title": title,
        "slug": f"blueprint-{item_id}",
        "status": "publish",
        "meta": {
            "_eve_bp_item_id": item_id,
            "_eve_bp_type_id": blueprint_data.get("type_id"),
            "_eve_bp_location_id": blueprint_data.get("location_id"),
            "_eve_bp_location_name": location_name,
            "_eve_bp_quantity": blueprint_data.get("quantity", -1),
            "_eve_bp_me": blueprint_data.get("material_efficiency", 0),
            "_eve_bp_te": blueprint_data.get("time_efficiency", 0),
            "_eve_bp_runs": blueprint_data.get("runs", -1),
            "_eve_char_id": char_id,
            "_eve_last_updated": datetime.now(timezone.utc).isoformat(),
        },
    }

    # Add featured image from type icon (only for new blueprints)
    if not existing_post:
        type_id = blueprint_data.get("type_id")
        if type_id:
            image_url = await fetch_type_icon(type_id, size=512)
            post_data["meta"]["_thumbnail_external_url"] = image_url

    if existing_post:
        # Check if data has changed before updating
        existing_meta = existing_post.get("meta", {})
        existing_title = existing_post.get("title", {}).get("rendered", "")

        # Compare key fields
        needs_update = (
            existing_title != title
            or str(existing_meta.get("_eve_bp_location_name", "")) != str(location_name)
            or str(existing_meta.get("_eve_bp_me", 0)) != str(me)
            or str(existing_meta.get("_eve_bp_te", 0)) != str(te)
            or str(existing_meta.get("_eve_bp_quantity", -1)) != str(quantity)
        )

        if not needs_update:
            logger.info(f"Blueprint {item_id} unchanged, skipping update")
            return

        # Update existing
        post_id = existing_post["id"]
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

        # Cache the new post ID if creation was successful
        if response.status_code in [200, 201]:
            new_post = response.json()
            set_cached_wp_post_id(wp_post_id_cache, "eve_blueprint", item_id, new_post["id"])

    if response.status_code in [200, 201]:
        logger.info(f"Updated blueprint: {item_id}")
    else:
        logger.error(f"Failed to update blueprint {item_id}: {response.status_code} - {response.text}")


def extract_blueprints_from_assets(
    assets_data: List[Dict[str, Any]], owner_type: str, owner_id: int, access_token: str, track_bpcs: bool = False
) -> List[Dict[str, Any]]:
    """Extract blueprint information from character or corporation assets data.

    Recursively processes asset lists to identify blueprints, filtering by type
    and ownership. By default only tracks BPOs (originals), optionally tracks BPCs.

    Args:
        assets_data: List of asset dictionaries from ESI API
        owner_type: Type of owner ('char' or 'corp')
        owner_id: Character or corporation ID
        access_token: Valid ESI access token (for structure lookups if needed)
        track_bpcs: Whether to include blueprint copies (default: False)

    Returns:
        List of blueprint dictionaries with standardized format

    Note:
        Recursively processes containers within assets.
        Uses blueprint type cache to avoid repeated ESI calls for type identification.
    """
    blueprint_type_cache = load_blueprint_type_cache()
    blueprints = []
    total_assets = len(assets_data) if assets_data else 0
    processed_count = 0

    logger.info(f"Processing {total_assets} {owner_type} assets for blueprint extraction...")

    def process_items(items: List[Dict[str, Any]], location_id: Optional[int]) -> None:
        nonlocal processed_count
        for item in items:
            processed_count += 1

            # Log progress every 1000 items
            if processed_count % 1000 == 0:
                logger.info(f"Processed {processed_count}/{total_assets} assets...")

            # Check if this is a blueprint (type_id corresponds to a blueprint)
            type_id = item.get("type_id")
            if type_id:
                type_id_str = str(type_id)
                if type_id_str in blueprint_type_cache:
                    is_blueprint = blueprint_type_cache[type_id_str]
                else:
                    type_data = fetch_public_esi(f"/universe/types/{type_id}")
                    is_blueprint = type_data and "Blueprint" in type_data.get("name", "")
                    blueprint_type_cache[type_id_str] = is_blueprint
                    save_blueprint_type_cache(blueprint_type_cache)

                if is_blueprint:
                    # Check if we should track this blueprint
                    quantity = item.get("quantity", 1)
                    is_bpo = quantity == -1

                    # Only track BPOs by default, or BPCs if explicitly requested
                    if is_bpo or track_bpcs:
                        # This is a blueprint
                        blueprint_info = {
                            "item_id": item.get("item_id"),
                            "type_id": type_id,
                            "location_id": location_id,
                            "quantity": quantity,
                            "material_efficiency": 0,  # Assets don't provide ME/TE info
                            "time_efficiency": 0,
                            "runs": -1,  # Assume BPO unless we can determine otherwise
                            "source": f"{owner_type}_assets",
                            "owner_id": owner_id,
                        }
                        blueprints.append(blueprint_info)
                    else:
                        # Skip BPCs - only track BPOs
                        logger.debug(f"Skipping BPC (quantity={quantity}) for item_id: {item.get('item_id')}")

            # Recursively process containers
            if "items" in item:
                process_items(item["items"], item.get("location_id", location_id))

    if assets_data:
        process_items(assets_data, None)

    logger.info(f"Completed asset processing: found {len(blueprints)} BPO blueprints in {total_assets} assets")
    return blueprints


def extract_blueprints_from_industry_jobs(
    jobs_data: List[Dict[str, Any]], owner_type: str, owner_id: int
) -> List[Dict[str, Any]]:
    """Extract blueprint information from active industry jobs.

    Processes industry job data to identify blueprints currently being used
    in manufacturing, copying, or invention activities.

    Args:
        jobs_data: List of industry job dictionaries from ESI API
        owner_type: Type of owner ('char' or 'corp')
        owner_id: Character or corporation ID

    Returns:
        List of blueprint dictionaries with ME/TE and runs information

    Note:
        Industry jobs always use blueprint originals (BPOs), never copies.
        Includes material and time efficiency levels from the job data.
    """
    return [
        {
            "item_id": job.get("blueprint_id"),
            "type_id": job.get("blueprint_type_id"),
            "location_id": job.get("station_id"),
            "quantity": -1,  # Jobs use BPOs
            "material_efficiency": job.get("material_efficiency", 0),
            "time_efficiency": job.get("time_efficiency", 0),
            "runs": job.get("runs", -1),
            "source": f"{owner_type}_industry_job",
            "owner_id": owner_id,
        }
        for job in jobs_data
        if job.get("blueprint_id") and job.get("blueprint_type_id")
    ]


def extract_blueprints_from_contracts(
    contracts_data: List[Dict[str, Any]], owner_type: str, owner_id: int
) -> List[Dict[str, Any]]:
    """Extract blueprint information from contract items.

    Processes contract item lists to identify blueprints being sold or traded.
    Only tracks blueprint originals (BPOs) as BPCs in contracts are typically consumable.

    Args:
        contracts_data: List of contract dictionaries with items from ESI API
        owner_type: Type of owner ('char' or 'corp')
        owner_id: Character or corporation ID

    Returns:
        List of blueprint dictionaries from contract items

    Note:
        Only includes BPOs (quantity == -1) from contracts.
        Contract blueprints don't include ME/TE information.
    """
    blueprint_type_cache = load_blueprint_type_cache()
    blueprints = []

    for contract in contracts_data:
        if "items" in contract:
            for item in contract["items"]:
                type_id = item.get("type_id")
                if type_id:
                    type_id_str = str(type_id)
                    if type_id_str in blueprint_type_cache:
                        is_blueprint = blueprint_type_cache[type_id_str]
                    else:
                        type_data = fetch_public_esi(f"/universe/types/{type_id}")
                        is_blueprint = type_data and "Blueprint" in type_data.get("name", "")
                        blueprint_type_cache[type_id_str] = is_blueprint
                        save_blueprint_type_cache(blueprint_type_cache)

                    if is_blueprint:
                        quantity = item.get("quantity", 1)
                        is_bpo = quantity == -1

                        # Only track BPOs from contracts (BPCs in contracts are typically for sale/consumable)
                        if is_bpo:
                            blueprint_info = {
                                "item_id": item.get("item_id", type_id),  # Contracts may not have item_id
                                "type_id": type_id,
                                "location_id": None,  # Contracts don't specify location
                                "quantity": quantity,
                                "material_efficiency": 0,  # Contract items don't provide ME/TE
                                "time_efficiency": 0,
                                "runs": -1,
                                "source": f"{owner_type}_contract_{contract.get('contract_id')}",
                                "owner_id": owner_id,
                            }
                            blueprints.append(blueprint_info)

    return blueprints


def update_blueprint_from_asset_in_wp(
    blueprint_data: Dict[str, Any],
    wp_post_id_cache: Dict[str, Any],
    char_id: int,
    access_token: str,
    blueprint_cache: Optional[Dict[str, Any]] = None,
    location_cache: Optional[Dict[str, Any]] = None,
    structure_cache: Optional[Dict[str, Any]] = None,
    failed_structures: Optional[Dict[str, Any]] = None,
) -> None:
    """Update or create blueprint post in WordPress from asset/industry/contract data.

    Creates WordPress posts for blueprints found in assets, industry jobs, or contracts.
    Handles location resolution for stations and structures, caching for performance.

    Args:
        blueprint_data: Blueprint information dictionary with standardized format
        wp_post_id_cache: Cache of WordPress post IDs for quick lookups
        char_id: Character ID for authentication (needed for structure access)
        access_token: Valid ESI access token
        blueprint_cache: Optional cache for blueprint type names
        location_cache: Optional cache for station/structure location names
        structure_cache: Optional cache for structure names
        failed_structures: Optional cache for structures that failed to load

    Returns:
        None

    Note:
        Only processes BPOs (originals), skips BPCs.
        Updates existing posts only if data has changed.
        Resolves location names for both public stations and private structures.
    """
    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()
    if location_cache is None:
        location_cache = load_location_cache()
    if structure_cache is None:
        structure_cache = load_structure_cache()
    if failed_structures is None:
        failed_structures = load_failed_structures()
    if wp_post_id_cache is None:
        wp_post_id_cache = load_wp_post_id_cache()

    item_id = blueprint_data["item_id"]

    # Skip BPCs - only track BPOs
    quantity = blueprint_data.get("quantity", -1)
    if quantity != -1:
        logger.info(f"Skipping BPC (quantity={quantity}) for item_id: {item_id}")
        return
    source = blueprint_data["source"]

    slug = f"blueprint-{item_id}"

    # Try to get post ID from cache first
    cached_post_id = get_cached_wp_post_id(wp_post_id_cache, "eve_blueprint", item_id)

    if cached_post_id:
        # Use direct post ID lookup
        response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{cached_post_id}", auth=get_wp_auth())
        if response.status_code == 200:
            existing_post = response.json()
        else:
            # Cache might be stale, fall back to slug lookup
            cached_post_id = None
            existing_post = None
    else:
        # Fall back to slug lookup
        response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint?slug={slug}", auth=get_wp_auth())
        existing_posts = response.json() if response.status_code == 200 else []
        existing_post = existing_posts[0] if existing_posts else None

        # Cache the post ID if found
        if existing_post:
            set_cached_wp_post_id(wp_post_id_cache, "eve_blueprint", item_id, existing_post["id"])

    # Get blueprint name and details
    type_id = blueprint_data.get("type_id")
    me = blueprint_data.get("material_efficiency", 0)
    te = blueprint_data.get("time_efficiency", 0)
    location_id = blueprint_data.get("location_id")
    quantity = blueprint_data.get("quantity", -1)

    # Get blueprint name from cache or API
    if type_id:
        if str(type_id) in blueprint_cache:
            type_name = blueprint_cache[str(type_id)]
        else:
            type_data = fetch_public_esi(f"/universe/types/{type_id}")
            if type_data:
                type_name = type_data.get("name", f"Blueprint {item_id}").replace(" Blueprint", "").strip()
                blueprint_cache[str(type_id)] = type_name
                save_blueprint_cache(blueprint_cache)
            else:
                type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()
    else:
        type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()

    # Determine BPO or BPC
    bp_type = "BPO" if quantity == -1 else "BPC"

    # Get location name from cache or API
    if location_id:
        location_id_str = str(location_id)
        if location_id_str in location_cache:
            location_name = location_cache[location_id_str]
        elif location_id >= 1000000000000:  # Structures (citadels, etc.)
            if location_id_str in failed_structures:
                location_name = f"Citadel {location_id}"
            elif location_id_str in structure_cache:
                location_name = structure_cache[location_id_str]
            else:
                # For corporation structures, we need a valid character ID for auth
                struct_data = fetch_esi(f"/universe/structures/{location_id}", char_id, access_token)
                if struct_data:
                    location_name = struct_data.get("name", f"Citadel {location_id}")
                    structure_cache[location_id_str] = location_name
                    save_structure_cache(structure_cache)
                else:
                    location_name = f"Citadel {location_id}"
                    failed_structures[location_id_str] = True
                    save_failed_structures(failed_structures)
        else:  # Stations - public
            if location_id_str in location_cache:
                location_name = location_cache[location_id_str]
            else:
                loc_data = fetch_public_esi(f"/universe/stations/{location_id}")
                location_name = loc_data.get("name", f"Station {location_id}") if loc_data else f"Station {location_id}"
                location_cache[location_id_str] = location_name
                save_location_cache(location_cache)
    else:
        location_name = f"From {source.replace('_', ' ').title()}"

    # Construct title
    title = f"{type_name} {bp_type} {me}/{te} ({location_name}) – ID: {item_id}"

    post_data = {
        "title": title,
        "slug": f"blueprint-{item_id}",
        "status": "publish",
        "meta": {
            "_eve_bp_item_id": item_id,
            "_eve_bp_type_id": blueprint_data.get("type_id"),
            "_eve_bp_location_id": blueprint_data.get("location_id"),
            "_eve_bp_location_name": location_name,
            "_eve_bp_quantity": blueprint_data.get("quantity", -1),
            "_eve_bp_me": blueprint_data.get("material_efficiency", 0),
            "_eve_bp_te": blueprint_data.get("time_efficiency", 0),
            "_eve_bp_runs": blueprint_data.get("runs", -1),
            "_eve_char_id": char_id,
            "_eve_last_updated": datetime.now(timezone.utc).isoformat(),
        },
    }

    # Add featured image from type icon (only for new blueprints)
    if not existing_post:
        type_id = blueprint_data.get("type_id")
        if type_id:
            image_url = fetch_type_icon(type_id, size=512)
            post_data["meta"]["_thumbnail_external_url"] = image_url

    if existing_post:
        # Check if data has changed before updating
        existing_meta = existing_post.get("meta", {})
        existing_title = existing_post.get("title", {}).get("rendered", "")

        # Compare key fields
        needs_update = (
            existing_title != title
            or str(existing_meta.get("_eve_bp_location_name", "")) != str(location_name)
            or str(existing_meta.get("_eve_bp_me", 0)) != str(me)
            or str(existing_meta.get("_eve_bp_te", 0)) != str(te)
            or str(existing_meta.get("_eve_bp_quantity", -1)) != str(quantity)
            or str(existing_meta.get("_eve_bp_source", "")) != str(source)
        )

        if not needs_update:
            logger.info(f"Blueprint from {source}: {item_id} unchanged, skipping update")
            return

        # Update existing
        post_id = existing_post["id"]
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

        # Cache the new post ID if creation was successful
        if response.status_code in [200, 201]:
            new_post = response.json()
            set_cached_wp_post_id(wp_post_id_cache, "eve_blueprint", item_id, new_post["id"])

    if response.status_code in [200, 201]:
        logger.info(f"Updated blueprint from {source}: {item_id}")
    else:
        logger.error(f"Failed to update blueprint {item_id} from {source}: {response.status_code} - {response.text}")


def cleanup_blueprint_posts() -> None:
    """
    Clean up blueprint posts that don't match filtering criteria.

    Removes BPC posts (only tracks BPOs), blueprints from unauthorized corporations,
    and orphaned blueprint posts without proper ownership information.

    Note:
        Preserves blueprints from authenticated sources and allowed corporations.
        Currently hardcoded to only allow No Mercy Incorporated corporation blueprints.
    """
    logger.info("Cleaning up blueprint posts...")

    response = requests.get(
        f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint", auth=get_wp_auth(), params={"per_page": WP_PER_PAGE}
    )
    if response.status_code == 200:
        blueprints = response.json()
        for bp in blueprints:
            meta = bp.get("meta", {})
            quantity = meta.get("_eve_bp_quantity", -1)
            owner_id = meta.get("_eve_bp_owner_id")
            source = meta.get("_eve_bp_source", "")
            char_id = meta.get("_eve_char_id")

            # Remove BPCs (we only want to track BPOs now)
            if quantity != -1:
                bp_id = meta.get("_eve_bp_item_id")
                logger.info(f"Deleting BPC (quantity={quantity}): {bp_id}")
                delete_wp_post("eve_blueprint", bp["id"])
                continue

            # If it's from a corporation, check if it's No Mercy incorporated
            if owner_id and source.startswith("corp_"):
                # We need to check if this corp_id belongs to No Mercy incorporated
                corp_response = requests.get(
                    f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation?meta_key=_eve_corp_id&meta_value={owner_id}",
                    auth=get_wp_auth(),
                )
                if corp_response.status_code == 200:
                    corp_posts = corp_response.json()
                    if not corp_posts:  # Corporation not found in our records
                        bp_id = bp.get("meta", {}).get("_eve_bp_item_id")
                        logger.info(f"Deleting blueprint from unknown corporation: {bp_id}")
                        delete_wp_post("eve_blueprint", bp["id"])
                    else:
                        corp_name = corp_posts[0].get("title", {}).get("rendered", "")
                        if corp_name.lower() != "no mercy incorporated":
                            bp_id = bp.get("meta", {}).get("_eve_bp_item_id")
                            logger.info(f"Deleting blueprint from {corp_name}: {bp_id}")
                            delete_wp_post("eve_blueprint", bp["id"])
            # If it's from character assets/industry jobs and we don't have a char_id, it might be orphaned
            elif not char_id and not owner_id:
                # These are from the direct blueprint endpoints - check if they're corporation blueprints
                # For now, keep them as they come from authenticated sources
                pass
