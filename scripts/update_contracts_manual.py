#!/usr/bin/env python3
"""
Update existing contracts with proper titles and thumbnails.
This script fetches contract items and generates descriptive titles for existing contracts.
"""

import os
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging
from config import *

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def load_tokens():
    """Load stored tokens."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return {}

def get_wp_auth():
    """Get WordPress authentication tuple."""
    return (WP_USERNAME, WP_APP_PASSWORD)

def fetch_character_contract_items(char_id, contract_id, access_token):
    """Fetch items in a specific character contract."""
    endpoint = f"/characters/{char_id}/contracts/{contract_id}/items/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_corporation_contract_items(corp_id, contract_id, access_token):
    """Fetch items in a specific corporation contract."""
    endpoint = f"/corporations/{corp_id}/contracts/{contract_id}/items/"
    return fetch_esi(endpoint, None, access_token)  # Corp endpoint doesn't need char_id

def fetch_public_esi(endpoint, max_retries=ESI_MAX_RETRIES):
    """Fetch data from ESI API (public endpoints, no auth) with rate limiting and error handling."""
    import time

    url = f"{ESI_BASE_URL}{endpoint}"

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=ESI_TIMEOUT)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.warning(f"Resource not found for public endpoint {endpoint}")
                return None
            elif response.status_code == 429:  # Rate limited
                # Check for X-ESI-Error-Limit-Remain header
                error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                if error_limit_reset:
                    wait_time = int(error_limit_reset) + 1  # Add 1 second buffer
                    logger.info(f"RATE LIMIT: Waiting {wait_time} seconds for public endpoint...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Fallback: wait 60 seconds if no reset header
                    logger.info(f"RATE LIMIT: Waiting 60 seconds for public endpoint (no reset header)...")
                    time.sleep(60)
                    continue
            elif response.status_code == 420:  # Error limited
                error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                if error_limit_reset:
                    wait_time = int(error_limit_reset) + 1
                    logger.info(f"ERROR LIMIT: Waiting {wait_time} seconds for public endpoint...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.info(f"ERROR LIMIT: Waiting 60 seconds for public endpoint...")
                    time.sleep(60)
                    continue
            elif response.status_code >= 500:
                # Server error, retry
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"SERVER ERROR {response.status_code}: Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"SERVER ERROR {response.status_code}: Max retries exceeded")
                    return None
            else:
                logger.error(f"ESI API error for {endpoint}: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"TIMEOUT: Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                logger.error("TIMEOUT: Max retries exceeded")
                return None
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"NETWORK ERROR: {e}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"NETWORK ERROR: {e}. Max retries exceeded")
                return None

    return None

def fetch_esi(endpoint, char_id, access_token, max_retries=ESI_MAX_RETRIES):
    """Fetch data from ESI API with rate limiting and error handling."""
    import time

    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {'Authorization': f'Bearer {access_token}'}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=ESI_TIMEOUT)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                logger.error(f"Authentication failed for endpoint {endpoint}")
                return None
            elif response.status_code == 403:
                logger.error(f"Access forbidden for endpoint {endpoint}")
                return None
            elif response.status_code == 404:
                logger.warning(f"Resource not found for endpoint {endpoint}")
                return None
            elif response.status_code == 429:  # Rate limited
                # Check for X-ESI-Error-Limit-Remain header
                error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                if error_limit_reset:
                    wait_time = int(error_limit_reset) + 1  # Add 1 second buffer
                    logger.info(f"RATE LIMIT: Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Fallback: wait 60 seconds if no reset header
                    logger.info(f"RATE LIMIT: Waiting 60 seconds (no reset header)...")
                    time.sleep(60)
                    continue
            elif response.status_code == 420:  # Error limited
                error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                if error_limit_reset:
                    wait_time = int(error_limit_reset) + 1
                    logger.info(f"ERROR LIMIT: Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.info(f"ERROR LIMIT: Waiting 60 seconds...")
                    time.sleep(60)
                    continue
            elif response.status_code >= 500:
                # Server error, retry
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"SERVER ERROR {response.status_code}: Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"SERVER ERROR {response.status_code}: Max retries exceeded")
                    return None
            else:
                logger.error(f"ESI API error for {endpoint}: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"TIMEOUT: Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                logger.error("TIMEOUT: Max retries exceeded")
                return None
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logger.warning(f"NETWORK ERROR: {e}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"NETWORK ERROR: {e}. Max retries exceeded")
                return None

    return None

def load_blueprint_cache():
    """Load blueprint name cache."""
    return load_cache(BLUEPRINT_CACHE_FILE)

def load_cache(cache_file):
    """Load cache from file."""
    ensure_cache_dir()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def ensure_cache_dir():
    """Ensure cache directory exists."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def fetch_type_icon(type_id, size=512):
    """Fetch type icon URL from images.evetech.net with fallback."""
    # Try the 'bp' variation first for blueprints, then fallback to regular icon
    variations = ['bp', 'icon']

    for variation in variations:
        icon_url = f"https://images.evetech.net/types/{type_id}/{variation}?size={size}"
        # Test if the URL exists by making a HEAD request
        try:
            response = requests.head(icon_url, timeout=5)
            if response.status_code == 200:
                return icon_url
        except:
            continue

    # If no icon found, return placeholder
    return f"https://via.placeholder.com/{size}x{size}/cccccc/000000?text=No+Icon"

def generate_contract_title(contract_data, contract_items=None, blueprint_cache=None):
    """Generate a descriptive contract title based on items."""
    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()

    contract_id = contract_data.get('contract_id')
    contract_type = contract_data.get('type', 'unknown')
    status = contract_data.get('status', 'unknown').title()

    # If no items, use default format
    if not contract_items:
        type_names = {
            'item_exchange': 'Item Exchange',
            'auction': 'Auction',
            'courier': 'Courier',
            'loan': 'Loan'
        }
        type_name = type_names.get(contract_type, contract_type.title())
        return f"Contract {contract_id} - {type_name} ({status})"

    # If we have items, create a more descriptive title
    if len(contract_items) == 1:
        # Single item contract
        item = contract_items[0]
        type_id = item.get('type_id')
        quantity = item.get('quantity', 1)

        if type_id:
            # Get item name
            if str(type_id) in blueprint_cache:
                item_name = blueprint_cache[str(type_id)]
            else:
                type_data = fetch_public_esi(f"/universe/types/{type_id}")
                if type_data:
                    item_name = type_data.get('name', f"Item {type_id}")
                    # Only cache if it's actually a blueprint
                    if 'Blueprint' in item_name:
                        cleaned_name = item_name.replace(" Blueprint", "").strip()
                        blueprint_cache[str(type_id)] = cleaned_name
                        save_blueprint_cache(blueprint_cache)
                else:
                    item_name = f"Item {type_id}"

            # Check if it's a blueprint (quantity -1 indicates BPO, or check if it's in blueprint cache)
            is_blueprint = str(type_id) in blueprint_cache
            if not is_blueprint:
                # Double-check with ESI if not in cache
                type_data = fetch_public_esi(f"/universe/types/{type_id}")
                is_blueprint = type_data and 'Blueprint' in type_data.get('name', '')

            if is_blueprint:
                bp_type = "BPO" if quantity == -1 else "BPC"
                return f"{item_name} {bp_type} - Contract {contract_id}"
            else:
                # Regular item
                return f"{item_name} (x{quantity}) - Contract {contract_id}"

    else:
        # Multiple items contract
        blueprint_count = 0
        total_quantity = 0

        for item in contract_items:
            quantity = item.get('quantity', 1)
            total_quantity += abs(quantity)  # Use abs in case of BPOs

            # Check if it's a blueprint
            type_id = item.get('type_id')
            if type_id:
                # First check if it's in blueprint cache
                if str(type_id) in blueprint_cache:
                    blueprint_count += 1
                else:
                    # Check with ESI
                    type_data = fetch_public_esi(f"/universe/types/{type_id}")
                    if type_data and 'Blueprint' in type_data.get('name', ''):
                        blueprint_count += 1

        if blueprint_count == len(contract_items):
            # All items are blueprints
            return f"{blueprint_count} Blueprints - Contract {contract_id}"
        elif blueprint_count > 0:
            # Mix of blueprints and other items
            return f"{blueprint_count} Blueprints + {len(contract_items) - blueprint_count} Items - Contract {contract_id}"
        else:
            # No blueprints, just regular items
            return f"{len(contract_items)} Items (x{total_quantity}) - Contract {contract_id}"

def save_blueprint_cache(cache):
    """Save blueprint name cache."""
    save_cache(BLUEPRINT_CACHE_FILE, cache)

def save_cache(cache_file, data):
    """Save cache to file."""
    ensure_cache_dir()
    with open(cache_file, 'w') as f:
        json.dump(data, f)

def update_existing_contract(contract_post, tokens):
    """Update an existing contract post with proper title and thumbnail."""
    meta = contract_post.get('meta', {})
    contract_id = meta.get('_eve_contract_id')
    for_corp = meta.get('_eve_contract_for_corp', 'false').lower() == 'true'
    
    # Determine entity_id based on contract type
    if for_corp:
        entity_id = meta.get('_eve_contract_issuer_corp_id')
    else:
        entity_id = meta.get('_eve_contract_issuer_id')

    if not contract_id or not entity_id:
        logger.warning(f"Contract post {contract_post['id']} missing contract_id or entity_id (contract_id: {contract_id}, entity_id: {entity_id})")
        return

    # Reconstruct contract data from meta
    contract_data = {
        'contract_id': contract_id,
        'type': meta.get('_eve_contract_type'),
        'status': meta.get('_eve_contract_status'),
        'issuer_id': meta.get('_eve_contract_issuer_id'),
        'issuer_corporation_id': meta.get('_eve_contract_issuer_corp_id'),
        'assignee_id': meta.get('_eve_contract_assignee_id'),
        'acceptor_id': meta.get('_eve_contract_acceptor_id'),
        'date_issued': meta.get('_eve_contract_date_issued'),
        'date_expired': meta.get('_eve_contract_date_expired'),
        'date_accepted': meta.get('_eve_contract_date_accepted'),
        'date_completed': meta.get('_eve_contract_date_completed'),
        'price': meta.get('_eve_contract_price'),
        'reward': meta.get('_eve_contract_reward'),
        'collateral': meta.get('_eve_contract_collateral'),
        'buyout': meta.get('_eve_contract_buyout'),
        'volume': meta.get('_eve_contract_volume'),
        'days_to_complete': meta.get('_eve_contract_days_to_complete'),
        'title': meta.get('_eve_contract_title')
    }

    # Find a valid access token for this entity
    access_token = None
    if for_corp:
        # For corporation contracts, try to find a token that can access corp contract items
        # Prioritize Dr FiLiN's token for No Mercy Incorporated
        if str(entity_id) == '98092220':  # No Mercy Incorporated
            # Find Dr FiLiN's token
            for char_id, token_data in tokens.items():
                try:
                    expired = datetime.now(timezone.utc) > datetime.fromisoformat(token_data.get('expires_at', '2000-01-01T00:00:00+00:00'))
                    if not expired and token_data.get('name') == 'Dr FiLiN':
                        # Test if this token can access corporation contract items
                        test_items = fetch_corporation_contract_items(entity_id, contract_id, token_data['access_token'])
                        if test_items is not None:  # Could be empty list, but not None (which means error)
                            access_token = token_data['access_token']
                            logger.info(f"Using Dr FiLiN's CEO token for No Mercy Incorporated contract {contract_id}")
                            break
                except:
                    continue
        
        # If Dr FiLiN's token didn't work or this isn't No Mercy, try other tokens
        if not access_token:
            for char_id, token_data in tokens.items():
                try:
                    expired = datetime.now(timezone.utc) > datetime.fromisoformat(token_data.get('expires_at', '2000-01-01T00:00:00+00:00'))
                    if not expired:
                        # Test if this token can access corporation contract items
                        test_items = fetch_corporation_contract_items(entity_id, contract_id, token_data['access_token'])
                        if test_items is not None:  # Could be empty list, but not None (which means error)
                            access_token = token_data['access_token']
                            char_name = token_data.get('name', f'Character {char_id}')
                            logger.info(f"Using {char_name}'s token for corporation contract {contract_id}")
                            break
                except:
                    continue
    else:
        # For character contracts, use the character's token directly
        if str(entity_id) in tokens:
            token_data = tokens[str(entity_id)]
            try:
                expired = datetime.now(timezone.utc) > datetime.fromisoformat(token_data.get('expires_at', '2000-01-01T00:00:00+00:00'))
                if not expired:
                    access_token = token_data['access_token']
            except:
                pass

    if not access_token:
        logger.warning(f"No valid access token found for contract {contract_id}, skipping item fetch")
        contract_items = None
    else:
        # Fetch contract items
        if for_corp:
            contract_items = fetch_corporation_contract_items(entity_id, contract_id, access_token)
        else:
            contract_items = fetch_character_contract_items(entity_id, contract_id, access_token)

    # Generate new title
    blueprint_cache = load_blueprint_cache()
    new_title = generate_contract_title(contract_data, contract_items, blueprint_cache)

    # Prepare update data
    update_data = {
        'title': new_title,
        'meta': {
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Add items data if available
    if contract_items:
        update_data['meta']['_eve_contract_items'] = json.dumps(contract_items)

        # Set thumbnail based on blueprint items in contract
        thumbnail_url = None
        for item in contract_items:
            type_id = item.get('type_id')
            if type_id:
                # Check if this is a blueprint
                type_data = fetch_public_esi(f"/universe/types/{type_id}")
                if type_data and 'Blueprint' in type_data.get('name', ''):
                    # Use the improved fetch_type_icon function
                    thumbnail_url = fetch_type_icon(type_id, size=512)
                    if thumbnail_url and not thumbnail_url.startswith('https://via.placeholder.com'):
                        break

        # If no blueprint icon found, use contract placeholder
        if not thumbnail_url:
            thumbnail_url = "https://via.placeholder.com/512x512/e74c3c/ffffff?text=Contract"

        # Check if thumbnail changed before updating
        existing_thumbnail = meta.get('_thumbnail_external_url')
        if existing_thumbnail != thumbnail_url:
            update_data['meta']['_thumbnail_external_url'] = thumbnail_url

    # Update the post
    post_id = contract_post['id']
    url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract/{post_id}"
    response = requests.put(url, json=update_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        logger.info(f"Updated contract {contract_id}: '{new_title}'")
    else:
        logger.error(f"Failed to update contract {contract_id}: {response.status_code} - {response.text}")

def main():
    """Update all existing contracts with proper titles and thumbnails."""
    logger.info("Starting manual contract update...")

    # Load tokens
    tokens = load_tokens()
    if not tokens:
        logger.error("No authorized characters found. Run 'python esi_oauth.py authorize' first.")
        return

    # Get all contract posts
    page = 1
    per_page = 100

    while True:
        response = requests.get(
            f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract",
            auth=get_wp_auth(),
            params={'per_page': per_page, 'page': page}
        )

        if response.status_code != 200:
            logger.error(f"Failed to fetch contracts page {page}: {response.status_code}")
            break

        contracts = response.json()
        if not contracts:
            break

        logger.info(f"Processing {len(contracts)} contracts from page {page}...")

        for contract in contracts:
            try:
                update_existing_contract(contract, tokens)
            except Exception as e:
                contract_id = contract.get('meta', {}).get('_eve_contract_id', 'unknown')
                logger.error(f"Error updating contract {contract_id}: {e}")

        page += 1

        # Check if we've reached the last page
        total_pages = int(response.headers.get('X-WP-TotalPages', 1))
        if page > total_pages:
            break

    logger.info("Contract update completed!")

if __name__ == "__main__":
    main()