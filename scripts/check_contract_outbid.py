#!/usr/bin/env python3
"""
Standalone contract outbid checker for EVE Observer.
Checks outstanding item exchange contracts for market competition and updates outbid status.
Run this script periodically (e.g., every 15-30 minutes) to monitor contract prices.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from api_client import (
    fetch_esi_sync,
    fetch_public_contract_items,
    fetch_public_contracts,
    fetch_public_esi_sync,
)
from config import TOKENS_FILE, WP_USERNAME, WP_APP_PASSWORD, WP_BASE_URL, ESI_BASE_URL
    fetch_public_esi_sync,
)
from config import TOKENS_FILE, WP_USERNAME, WP_APP_PASSWORD, WP_BASE_URL

# Additional configuration
ESI_VERSION = "latest"
ALLOWED_CORP_IDS = {98092220}  # No Mercy Incorporated

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("eve_observer.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Setup requests session with retry strategy
session = requests.Session()
retry_strategy = Retry(total=3, status_forcelist=[429, 500, 502, 503, 504], backoff_factor=1)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)


def load_cache(cache_file):
    """Load cache from JSON file."""
    try:
        with open(cache_file, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache_file, data):
    """Save cache to JSON file."""
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)


def load_tokens():
    """Load ESI tokens from file."""
    try:
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.error("No tokens file found. Run 'python esi_oauth.py authorize' first.")
        return {}


def get_wp_auth():
    """Get WordPress authentication tuple."""
    return (WP_USERNAME, WP_APP_PASSWORD)


def refresh_token(refresh_token):
    """Refresh an access token."""
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    client_id = os.getenv("ESI_CLIENT_ID")
    client_secret = os.getenv("ESI_CLIENT_SECRET")
    response = requests.post("https://login.eveonline.com/v2/oauth/token", data=data, auth=(client_id, client_secret))
    if response.status_code == 200:
        token_data = response.json()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", refresh_token),
            "expires_at": expires_at.isoformat(),
        }
    else:
        logger.error(f"Failed to refresh token: {response.status_code} - {response.text}")
        return None


def save_tokens(tokens):
    """Save tokens to file."""
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def check_contract_competition(contract_data, contract_items):
    """Check if a sell contract has been outbid by cheaper competing contracts in the same region."""
    if not contract_items or len(contract_items) != 1:
        return False, None  # Only check single item contracts

    contract_type = contract_data.get("type")
    if contract_type != "item_exchange":
        return False, None  # Only check sell orders

    item = contract_items[0]
    type_id = item.get("type_id")
    quantity = item.get("quantity", 1)
    contract_price = contract_data.get("price", 0)
    contract_id = contract_data.get("contract_id")
    contract_issuer_id = contract_data.get("issuer_id")

    if not type_id or quantity <= 0 or contract_price <= 0:
        return False, None

    price_per_item = contract_price / quantity

    # Get contract region from start_location_id
    start_location_id = contract_data.get("start_location_id")
    if not start_location_id:
        logger.warning(f"Contract {contract_id} missing start_location_id, skipping contract competition check")
        return False, None

    region_id = None
    if start_location_id >= 1000000000000:  # Structure
        # For structures, we need to fetch structure info to get solar_system_id, then region
        struct_data = fetch_public_esi_sync(f"/universe/structures/{start_location_id}")
        if struct_data:
            solar_system_id = struct_data.get("solar_system_id")
            if solar_system_id:
                system_data = fetch_public_esi_sync(f"/universe/systems/{solar_system_id}")
                if system_data:
                    constellation_id = system_data.get("constellation_id")
                    if constellation_id:
                        constellation_data = fetch_public_esi_sync(f"/universe/constellations/{constellation_id}")
                        if constellation_data:
                            region_id = constellation_data.get("region_id")
    else:  # Station
        station_data = fetch_public_esi_sync(f"/universe/stations/{start_location_id}")
        if station_data:
            system_id = station_data.get("system_id")
            if system_id:
                system_data = fetch_public_esi_sync(f"/universe/systems/{system_id}")
                if system_data:
                    constellation_id = system_data.get("constellation_id")
                    if constellation_id:
                        constellation_data = fetch_public_esi_sync(f"/universe/constellations/{constellation_id}")
                        if constellation_data:
                            region_id = constellation_data.get("region_id")

    if not region_id:
        return False, None

    logger.info(f"Checking competition for contract {contract_id} (type_id: {type_id}, price_per_item: {price_per_item:.2f}) in region {region_id}")

    # OPTIMIZATION: Only fetch item_exchange contracts and limit to first few pages
    # Define price range to check (50% to 200% of our contract price to avoid irrelevant contracts)
    min_price = price_per_item * 0.5
    max_price = price_per_item * 2.0

    competing_prices = []
    max_pages_to_check = 3  # Limit to first 3 pages (3000 contracts max)
    max_competing_to_check = 20  # Early exit after finding 20 competing contracts

    for page in range(1, max_pages_to_check + 1):
        # Fetch only item_exchange contracts for this page
        page_contracts = fetch_public_contracts(region_id, page=page, contract_type="item_exchange")
        if not page_contracts:
            break

        logger.debug(f"Fetched {len(page_contracts)} contracts from page {page} in region {region_id}")

        # Filter contracts on this page
        for comp_contract in page_contracts:
            if comp_contract.get("type") != "item_exchange":
                continue
            if comp_contract.get("status") != "outstanding":
                continue
            if comp_contract.get("contract_id") == contract_id:
                continue
            if comp_contract.get("issuer_id") == contract_issuer_id:
                continue

            comp_price = comp_contract.get("price", 0)
            if comp_price <= 0:
                continue

            # Quick price range check before fetching items (avoids API calls for irrelevant contracts)
            comp_price_per_item = comp_price / max(comp_contract.get("volume", 1), 1)
            if comp_price_per_item < min_price or comp_price_per_item > max_price:
                continue

            # Fetch contract items to verify it contains the same item
            comp_contract_id = comp_contract.get("contract_id")
            comp_items = fetch_public_contract_items(comp_contract_id)

            if comp_items and len(comp_items) == 1:
                comp_item = comp_items[0]
                if comp_item.get("type_id") == type_id:
                    comp_quantity = comp_item.get("quantity", 1)
                    if comp_quantity > 0:
                        final_comp_price_per_item = comp_price / comp_quantity
                        competing_prices.append(final_comp_price_per_item)

                        # Early exit if we have enough competing contracts to check
                        if len(competing_prices) >= max_competing_to_check:
                            logger.debug(f"Found {len(competing_prices)} competing contracts, stopping early")
                            break

        # Check if we hit the page limit
        if len(page_contracts) < 1000:  # ESI returns max 1000 per page
            break  # No more pages available

        if len(competing_prices) >= max_competing_to_check:
            break

    if not competing_prices:
        logger.debug(f"No competing contracts found for contract {contract_id}")
        return False, None

    # Find the lowest competing price
    lowest_competing_price = min(competing_prices)

    logger.debug(f"Found {len(competing_prices)} competing contracts, lowest price: {lowest_competing_price:.2f}")

    if lowest_competing_price < price_per_item:
        return True, lowest_competing_price

    return False, None


def update_contract_outbid_status(contract_id, is_outbid, competing_price=None):
    """Update only the outbid status and competing price of a contract."""
    slug = f"contract-{contract_id}"

    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    if not existing_post:
        logger.warning(f"Contract {contract_id} not found in WordPress")
        return

    existing_meta = existing_post.get("meta", {})
    existing_outbid = existing_meta.get("_eve_contract_outbid") == "1"

    # Only update if outbid status has changed
    if existing_outbid == is_outbid:
        logger.debug(f"Contract {contract_id} outbid status unchanged ({is_outbid})")
        return

    # Prepare update data
    post_data = {
        "meta": {
            "_eve_contract_outbid": "1" if is_outbid else "0",
            "_eve_last_updated": datetime.now(timezone.utc).isoformat(),
        }
    }

    if is_outbid and competing_price:
        post_data["meta"]["_eve_contract_competing_price"] = str(competing_price)
        logger.warning(f"Contract {contract_id} is outbid by competing contract price: {competing_price}")
    elif not is_outbid:
        # Remove competing price if no longer outbid
        post_data["meta"]["_eve_contract_competing_price"] = None


def collect_corporation_members(tokens):
    """Collect all corporations and their member characters from authorized tokens."""
    corp_members = {}
    for char_id_str, token_data in tokens.items():
        char_id = int(char_id_str)  # Convert string key to int
        try:
            expired = datetime.now(timezone.utc) > datetime.fromisoformat(
                token_data.get("expires_at", "2000-01-01T00:00:00+00:00")
            )
        except (ValueError, TypeError):
            expired = True
        if expired:
            new_token = refresh_token(token_data["refresh_token"])
            if new_token:
                token_data.update(new_token)
                save_tokens(tokens)
            else:
                logger.warning(f"Failed to refresh token for {token_data['name']}")
                continue

        access_token = token_data["access_token"]
        char_name = token_data["name"]

        # Fetch basic character data to get corporation
        char_data = fetch_character_data_sync(char_id, access_token)
        if char_data:
            corp_id = char_data.get("corporation_id")
            if corp_id:
                if corp_id not in corp_members:
                    corp_members[corp_id] = []
                corp_members[corp_id].append((char_id, access_token, char_name))

    return corp_members


def fetch_character_data_sync(char_id, access_token):
    """Fetch character data synchronously."""
    endpoint = f"/characters/{char_id}/"
    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt < 2:
                time.sleep(2**attempt)
            else:
                logger.error(f"Failed to fetch character data: {e}")
                return None


def fetch_corporation_contracts(corp_id, access_token):
    """Fetch corporation contracts."""
    return fetch_esi_sync(f"/corporations/{corp_id}/contracts/", corp_id, access_token)


def fetch_character_contracts(char_id, access_token):
    """Fetch character contracts."""
    return fetch_esi_sync(f"/characters/{char_id}/contracts/", char_id, access_token)


def check_contract_outbid_status(contract, for_corp, entity_id, access_token):
    """Check and update outbid status for a single contract."""
    contract_id = contract.get("contract_id")
    contract_status = contract.get("status")
    contract_type = contract.get("type")

    # Only check outstanding item exchange contracts
    if contract_status != "outstanding" or contract_type != "item_exchange":
        return

    logger.debug(f"Checking outbid status for contract {contract_id}")

    # Get contract items
    if for_corp:
        items = fetch_esi_sync(f"/corporations/{entity_id}/contracts/{contract_id}/items/", entity_id, access_token)
    else:
        items = fetch_esi_sync(f"/characters/{entity_id}/contracts/{contract_id}/items/", entity_id, access_token)

    if not items:
        return

    # Check contract competition
    is_outbid, competing_price = check_contract_competition(contract, items)
    update_contract_outbid_status(contract_id, is_outbid, competing_price)


def main():
    """Main outbid checking routine."""
    logger.info("Starting contract outbid status check...")

    tokens = load_tokens()
    if not tokens:
        logger.error("No authorized characters found.")
        return

    # Collect all corporations and their member characters
    corp_members = collect_corporation_members(tokens)

    # Define allowed issuers for contract filtering
    allowed_issuer_ids = set()
    for corp_id, members in corp_members.items():
        if corp_id in ALLOWED_CORP_IDS:
            for char_id, access_token, char_name in members:
                allowed_issuer_ids.add(char_id)

    # Check corporation contracts
    for corp_id, members in corp_members.items():
        if corp_id not in ALLOWED_CORP_IDS:
            continue

        # Use the first available member token for corporation contracts
        if members:
            char_id, access_token, char_name = members[0]
            logger.info(f"Checking corporation contracts for corp {corp_id} using {char_name}'s token")

            corp_contracts = fetch_corporation_contracts(corp_id, access_token)
            if corp_contracts:
                logger.info(f"Checking {len(corp_contracts)} corporation contracts for outbid status")
                for contract in corp_contracts:
                    check_contract_outbid_status(contract, True, corp_id, access_token)

    # Check character contracts
    for char_id_str, token_data in tokens.items():
        char_id = int(char_id_str)  # Convert string key to int
        if char_id not in allowed_issuer_ids:
            continue

        access_token = token_data["access_token"]
        char_name = token_data["name"]
        logger.info(f"Checking character contracts for {char_name}")

        char_contracts = fetch_character_contracts(char_id, access_token)
        if char_contracts:
            logger.info(f"Checking {len(char_contracts)} character contracts for outbid status")
            for contract in char_contracts:
                check_contract_outbid_status(contract, False, char_id, access_token)

    logger.info("Contract outbid status check completed.")


if __name__ == "__main__":
    main()
