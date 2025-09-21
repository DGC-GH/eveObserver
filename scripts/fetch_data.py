#!/usr/bin/env python3
"""
EVE Observer Data Fetcher
Fetches data from EVE ESI API and stores in WordPress database via REST API.
"""

import os
import json
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
import logging
from config import *
from esi_oauth import save_tokens

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
# WordPress post ID cache
WP_POST_ID_CACHE_FILE = os.path.join(CACHE_DIR, 'wp_post_ids.json')

def load_tokens():
    """Load stored tokens."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return {}

def ensure_cache_dir():
    """Ensure cache directory exists."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

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

def save_cache(cache_file, data):
    """Save cache to file."""
    ensure_cache_dir()
    with open(cache_file, 'w') as f:
        json.dump(data, f)

def load_blueprint_cache():
    """Load blueprint name cache."""
    return load_cache(BLUEPRINT_CACHE_FILE)

def save_blueprint_cache(cache):
    """Save blueprint name cache."""
    save_cache(BLUEPRINT_CACHE_FILE, cache)

def load_blueprint_type_cache():
    """Load blueprint type cache."""
    return load_cache(BLUEPRINT_TYPE_CACHE_FILE)

def save_blueprint_type_cache(cache):
    """Save blueprint type cache."""
    save_cache(BLUEPRINT_TYPE_CACHE_FILE, cache)

def load_location_cache():
    """Load location name cache."""
    return load_cache(LOCATION_CACHE_FILE)

def save_location_cache(cache):
    """Save location name cache."""
    save_cache(LOCATION_CACHE_FILE, cache)

def load_structure_cache():
    """Load structure name cache."""
    return load_cache(STRUCTURE_CACHE_FILE)

def save_structure_cache(cache):
    """Save structure name cache."""
    save_cache(STRUCTURE_CACHE_FILE, cache)

def load_failed_structures():
    """Load failed structures cache."""
    return load_cache(FAILED_STRUCTURES_FILE)

def load_wp_post_id_cache():
    """Load WordPress post ID cache."""
    return load_cache(WP_POST_ID_CACHE_FILE)

def save_wp_post_id_cache(cache):
    """Save WordPress post ID cache."""
    save_cache(WP_POST_ID_CACHE_FILE, cache)

def get_cached_wp_post_id(cache, post_type, item_id):
    """Get cached WordPress post ID for an item."""
    key = f"{post_type}_{item_id}"
    return cache.get(key)

def set_cached_wp_post_id(cache, post_type, item_id, post_id):
    """Cache WordPress post ID for an item."""
    key = f"{post_type}_{item_id}"
    cache[key] = post_id
    save_wp_post_id_cache(cache)

def process_blueprints_parallel(blueprints, update_func, wp_post_id_cache, *args, **kwargs):
    """Process blueprints in parallel while respecting rate limits."""
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
    import time
    import logging

    max_workers = ESI_MAX_WORKERS  # Limit concurrent requests to avoid rate limiting
    results = []
    processed_count = 0
    total_blueprints = len(blueprints)

    logger.info(f"Starting parallel processing of {total_blueprints} blueprints with {max_workers} workers")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all blueprint update tasks
        future_to_bp = {
            executor.submit(update_func, bp, wp_post_id_cache, *args, **kwargs): bp
            for bp in blueprints
        }

        for future in as_completed(future_to_bp):
            bp = future_to_bp[future]
            item_id = bp.get("item_id", "unknown")
            processed_count += 1

            try:
                # Add timeout to prevent hanging
                result = future.result(timeout=300)  # 5 minute timeout per blueprint
                results.append(result)
                logger.info(f"Processed blueprint {processed_count}/{total_blueprints}: {item_id}")

                # Small delay between requests to be rate limit friendly
                time.sleep(0.1)

            except TimeoutError:
                logger.error(f"Blueprint {item_id} timed out after 5 minutes - skipping")
                # Cancel the future if possible
                if not future.cancelled():
                    future.cancel()

            except Exception as exc:
                logger.error(f'Blueprint {item_id} generated an exception: {exc}')
                logger.error(f'Blueprint data: {bp}')
                # Continue processing other blueprints

    logger.info(f"Completed parallel processing: {len(results)}/{total_blueprints} blueprints processed successfully")
    return results

def send_email(subject, body):
    """Send an email alert."""
    if not all([EMAIL_SMTP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO]):
        logger.warning("Email configuration incomplete, skipping alert.")
        return

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO

    try:
        server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        server.quit()
        logger.info(f"Alert email sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

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

def get_wp_auth():
    """Get WordPress authentication tuple."""
    return (WP_USERNAME, WP_APP_PASSWORD)

def delete_wp_post(post_type, post_id):
    """Delete a WordPress post."""
    url = f"{WP_BASE_URL}/wp-json/wp/v2/{post_type}/{post_id}"
    response = requests.delete(url, auth=get_wp_auth())
    if response.status_code == 200:
        logger.info(f"Deleted {post_type} post: {post_id}")
    else:
        logger.error(f"Failed to delete {post_type} post {post_id}: {response.status_code} - {response.text}")

def update_character_in_wp(char_id, char_data):
    """Update or create character post in WordPress."""
    slug = f"character-{char_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_character?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    post_data = {
        'title': char_data['name'],
        'slug': f"character-{char_id}",
        'status': 'publish',
        'meta': {
            '_eve_char_id': char_id,
            '_eve_char_name': char_data['name'],
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Add optional fields if they exist
    optional_fields = {
        '_eve_corporation_id': char_data.get('corporation_id'),
        '_eve_alliance_id': char_data.get('alliance_id'),
        '_eve_birthday': char_data.get('birthday'),
        '_eve_gender': char_data.get('gender'),
        '_eve_race_id': char_data.get('race_id'),
        '_eve_bloodline_id': char_data.get('bloodline_id'),
        '_eve_ancestry_id': char_data.get('ancestry_id'),
        '_eve_security_status': char_data.get('security_status')
    }
    for key, value in optional_fields.items():
        if value is not None:
            post_data['meta'][key] = value

    # Add featured image from character portrait
    portrait_data = fetch_character_portrait(char_id)
    if portrait_data and 'px256x256' in portrait_data:
        new_portrait_url = portrait_data['px256x256']
        # Check if portrait changed before updating
        existing_portrait_url = existing_post.get('meta', {}).get('_thumbnail_external_url') if existing_post else None
        if existing_portrait_url != new_portrait_url:
            post_data['meta']['_thumbnail_external_url'] = new_portrait_url
            logger.info(f"Updated portrait for character: {char_data['name']}")
        else:
            logger.info(f"Portrait unchanged for character: {char_data['name']}")

    if existing_post:
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_character/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_character"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        logger.info(f"Updated character: {char_data['name']}")
    else:
        logger.error(f"Failed to update character {char_data['name']}: {response.status_code} - {response.text}")

def update_character_skills_in_wp(char_id, skills_data):
    """Update character post with skills data."""
    slug = f"character-{char_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_character?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    if existing_post:
        post_id = existing_post['id']
        # Update with skills data
        post_data = {
            'meta': {
                '_eve_total_sp': skills_data.get('total_sp', 0),
                '_eve_last_updated': datetime.now(timezone.utc).isoformat()
            }
        }
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_character/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
        if response.status_code in [200, 201]:
            logger.info(f"Updated skills for character {char_id}")
        else:
            logger.error(f"Failed to update skills for character {char_id}: {response.status_code} - {response.text}")

def fetch_character_data(char_id, access_token):
    """Fetch basic character data from ESI."""
    endpoint = f"/characters/{char_id}/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_character_skills(char_id, access_token):
    """Fetch character skills."""
    endpoint = f"/characters/{char_id}/skills/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_character_blueprints(char_id, access_token):
    """Fetch character blueprints."""
    endpoint = f"/characters/{char_id}/blueprints/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_character_planets(char_id, access_token):
    """Fetch character planets."""
    endpoint = f"/characters/{char_id}/planets/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_corporation_data(corp_id, access_token):
    """Fetch corporation data from ESI."""
    endpoint = f"/corporations/{corp_id}/"
    return fetch_esi(endpoint, None, access_token)  # No char_id needed for corp data

def update_blueprint_in_wp(blueprint_data, wp_post_id_cache, char_id, access_token, blueprint_cache=None, location_cache=None, structure_cache=None, failed_structures=None):
    """Update or create blueprint post in WordPress."""
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

    item_id = blueprint_data.get('item_id')
    if not item_id:
        logger.error(f"Blueprint data missing item_id: {blueprint_data}")
        return

    # Skip BPCs - only track BPOs
    quantity = blueprint_data.get('quantity', -1)
    if quantity != -1:
        logger.info(f"Skipping BPC (quantity={quantity}) for item_id: {item_id}")
        return

    slug = f"blueprint-{item_id}"
    
    # Try to get post ID from cache first
    cached_post_id = get_cached_wp_post_id(wp_post_id_cache, 'eve_blueprint', item_id)
    
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
            set_cached_wp_post_id(wp_post_id_cache, 'eve_blueprint', item_id, existing_post['id'])

    # Get blueprint name and details
    type_id = blueprint_data.get('type_id')
    me = blueprint_data.get('material_efficiency', 0)
    te = blueprint_data.get('time_efficiency', 0)
    location_id = blueprint_data.get('location_id')
    quantity = blueprint_data.get('quantity', -1)
    
    # Get blueprint name from cache or API
    if type_id:
        if str(type_id) in blueprint_cache:
            type_name = blueprint_cache[str(type_id)]
        else:
            type_data = fetch_public_esi(f"/universe/types/{type_id}")
            if type_data:
                type_name = type_data.get('name', f"Blueprint {item_id}").replace(" Blueprint", "").strip()
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
                # Try auth fetch
                struct_data = fetch_esi(f"/universe/structures/{location_id}", char_id, access_token)
                if struct_data:
                    location_name = struct_data.get('name', f"Citadel {location_id}")
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
                location_name = loc_data.get('name', f"Station {location_id}") if loc_data else f"Station {location_id}"
                location_cache[location_id_str] = location_name
                save_location_cache(location_cache)
    else:
        location_name = "Unknown Location"
    
    # Construct title
    title = f"{type_name} {bp_type} {me}/{te} ({location_name}) – ID: {item_id}"

    post_data = {
        'title': title,
        'slug': f"blueprint-{item_id}",
        'status': 'publish',
        'meta': {
            '_eve_bp_item_id': item_id,
            '_eve_bp_type_id': blueprint_data.get('type_id'),
            '_eve_bp_location_id': blueprint_data.get('location_id'),
            '_eve_bp_location_name': location_name,
            '_eve_bp_quantity': blueprint_data.get('quantity', -1),
            '_eve_bp_me': blueprint_data.get('material_efficiency', 0),
            '_eve_bp_te': blueprint_data.get('time_efficiency', 0),
            '_eve_bp_runs': blueprint_data.get('runs', -1),
            '_eve_char_id': char_id,
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Add featured image from type icon (only for new blueprints)
    if not existing_post:
        type_id = blueprint_data.get('type_id')
        if type_id:
            image_url = fetch_type_icon(type_id, size=512)
            post_data['meta']['_thumbnail_external_url'] = image_url

    if existing_post:
        # Check if data has changed before updating
        existing_meta = existing_post.get('meta', {})
        existing_title = existing_post.get('title', {}).get('rendered', '')
        
        # Compare key fields
        needs_update = (
            existing_title != title or
            str(existing_meta.get('_eve_bp_location_name', '')) != str(location_name) or
            str(existing_meta.get('_eve_bp_me', 0)) != str(me) or
            str(existing_meta.get('_eve_bp_te', 0)) != str(te) or
            str(existing_meta.get('_eve_bp_quantity', -1)) != str(quantity)
        )
        
        if not needs_update:
            logger.info(f"Blueprint {item_id} unchanged, skipping update")
            return
        
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint"
        response = requests.post(url, json=post_data, auth=get_wp_auth())
        
        # Cache the new post ID if creation was successful
        if response.status_code in [200, 201]:
            new_post = response.json()
            set_cached_wp_post_id(wp_post_id_cache, 'eve_blueprint', item_id, new_post['id'])

    if response.status_code in [200, 201]:
        logger.info(f"Updated blueprint: {item_id}")
    else:
        logger.error(f"Failed to update blueprint {item_id}: {response.status_code} - {response.text}")

def fetch_character_assets(char_id, access_token):
    """Fetch character assets."""
    endpoint = f"/characters/{char_id}/assets/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_character_contracts(char_id, access_token):
    """Fetch character contracts."""
    endpoint = f"/characters/{char_id}/contracts/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_character_contract_items(char_id, contract_id, access_token):
    """Fetch items in a specific character contract."""
    endpoint = f"/characters/{char_id}/contracts/{contract_id}/items/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_corporation_blueprints(corp_id, access_token):
    """Fetch corporation blueprints."""
    endpoint = f"/corporations/{corp_id}/blueprints/"
    return fetch_esi(endpoint, corp_id, access_token)

def fetch_corporation_contracts(corp_id, access_token):
    """Fetch corporation contracts."""
    endpoint = f"/corporations/{corp_id}/contracts/"
    return fetch_esi(endpoint, None, access_token)  # Corp contracts don't need char_id

def fetch_corporation_contract_items(corp_id, contract_id, access_token):
    """Fetch items in a specific corporation contract."""
    endpoint = f"/corporations/{corp_id}/contracts/{contract_id}/items/"
    return fetch_esi(endpoint, None, access_token)  # Corp endpoint doesn't need char_id

def fetch_corporation_industry_jobs(corp_id, access_token):
    """Fetch corporation industry jobs."""
    endpoint = f"/corporations/{corp_id}/industry/jobs/"
    return fetch_esi(endpoint, corp_id, access_token)

def extract_blueprints_from_assets(assets_data, owner_type, owner_id, access_token, track_bpcs=False):
    """Extract blueprint information from assets data."""
    blueprint_type_cache = load_blueprint_type_cache()
    blueprints = []
    total_assets = len(assets_data) if assets_data else 0
    processed_count = 0
    
    logger.info(f"Processing {total_assets} {owner_type} assets for blueprint extraction...")
    
    def process_items(items, location_id):
        nonlocal processed_count
        for item in items:
            processed_count += 1
            
            # Log progress every 1000 items
            if processed_count % 1000 == 0:
                logger.info(f"Processed {processed_count}/{total_assets} assets...")
            
            # Check if this is a blueprint (type_id corresponds to a blueprint)
            type_id = item.get('type_id')
            if type_id:
                type_id_str = str(type_id)
                if type_id_str in blueprint_type_cache:
                    is_blueprint = blueprint_type_cache[type_id_str]
                else:
                    type_data = fetch_public_esi(f"/universe/types/{type_id}")
                    is_blueprint = type_data and 'Blueprint' in type_data.get('name', '')
                    blueprint_type_cache[type_id_str] = is_blueprint
                    save_blueprint_type_cache(blueprint_type_cache)
                
                if is_blueprint:
                    # Check if we should track this blueprint
                    quantity = item.get('quantity', 1)
                    is_bpo = quantity == -1
                    
                    # Only track BPOs by default, or BPCs if explicitly requested
                    if is_bpo or track_bpcs:
                        # This is a blueprint
                        blueprint_info = {
                            'item_id': item.get('item_id'),
                            'type_id': type_id,
                            'location_id': location_id,
                            'quantity': quantity,
                            'material_efficiency': 0,  # Assets don't provide ME/TE info
                            'time_efficiency': 0,
                            'runs': -1,  # Assume BPO unless we can determine otherwise
                            'source': f"{owner_type}_assets",
                            'owner_id': owner_id
                        }
                        blueprints.append(blueprint_info)
            
            # Recursively process containers
            if 'items' in item:
                process_items(item['items'], item.get('location_id', location_id))
    
    if assets_data:
        process_items(assets_data, None)
    
    logger.info(f"Completed asset processing: found {len(blueprints)} blueprints in {total_assets} assets")
    return blueprints

def extract_blueprints_from_industry_jobs(jobs_data, owner_type, owner_id):
    """Extract blueprint information from industry jobs."""
    blueprints = []
    
    for job in jobs_data:
        blueprint_id = job.get('blueprint_id')
        blueprint_type_id = job.get('blueprint_type_id')
        if blueprint_id and blueprint_type_id:
            # Industry jobs typically use BPOs (quantity = -1)
            blueprint_info = {
                'item_id': blueprint_id,
                'type_id': blueprint_type_id,
                'location_id': job.get('station_id'),
                'quantity': -1,  # Jobs use BPOs
                'material_efficiency': job.get('material_efficiency', 0),
                'time_efficiency': job.get('time_efficiency', 0),
                'runs': job.get('runs', -1),
                'source': f"{owner_type}_industry_job",
                'owner_id': owner_id
            }
            blueprints.append(blueprint_info)
    
    return blueprints

def extract_blueprints_from_contracts(contracts_data, owner_type, owner_id):
    """Extract blueprint information from contracts."""
    blueprint_type_cache = load_blueprint_type_cache()
    blueprints = []
    
    for contract in contracts_data:
        if 'items' in contract:
            for item in contract['items']:
                type_id = item.get('type_id')
                if type_id:
                    type_id_str = str(type_id)
                    if type_id_str in blueprint_type_cache:
                        is_blueprint = blueprint_type_cache[type_id_str]
                    else:
                        type_data = fetch_public_esi(f"/universe/types/{type_id}")
                        is_blueprint = type_data and 'Blueprint' in type_data.get('name', '')
                        blueprint_type_cache[type_id_str] = is_blueprint
                        save_blueprint_type_cache(blueprint_type_cache)
                    
                    if is_blueprint:
                        quantity = item.get('quantity', 1)
                        is_bpo = quantity == -1
                        
                        # Only track BPOs from contracts (BPCs in contracts are typically for sale/consumable)
                        if is_bpo:
                            blueprint_info = {
                                'item_id': item.get('item_id', type_id),  # Contracts may not have item_id
                                'type_id': type_id,
                                'location_id': None,  # Contracts don't specify location
                                'quantity': quantity,
                                'material_efficiency': 0,  # Contract items don't provide ME/TE
                                'time_efficiency': 0,
                                'runs': -1,
                                'source': f"{owner_type}_contract_{contract.get('contract_id')}",
                                'owner_id': owner_id
                            }
                            blueprints.append(blueprint_info)
    
    return blueprints

def update_blueprint_from_asset_in_wp(blueprint_data, wp_post_id_cache, char_id, access_token, blueprint_cache=None, location_cache=None, structure_cache=None, failed_structures=None):
    """Update or create blueprint post from asset/industry/contract data."""
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

    item_id = blueprint_data['item_id']
    
    # Skip BPCs - only track BPOs
    quantity = blueprint_data.get('quantity', -1)
    if quantity != -1:
        logger.info(f"Skipping BPC (quantity={quantity}) for item_id: {item_id}")
        return
    owner_id = blueprint_data['owner_id']
    source = blueprint_data['source']
    
    slug = f"blueprint-{item_id}"
    
    # Try to get post ID from cache first
    cached_post_id = get_cached_wp_post_id(wp_post_id_cache, 'eve_blueprint', item_id)
    
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
            set_cached_wp_post_id(wp_post_id_cache, 'eve_blueprint', item_id, existing_post['id'])

    # Get blueprint name and details
    type_id = blueprint_data.get('type_id')
    me = blueprint_data.get('material_efficiency', 0)
    te = blueprint_data.get('time_efficiency', 0)
    location_id = blueprint_data.get('location_id')
    quantity = blueprint_data.get('quantity', -1)
    
    # Get blueprint name from cache or API
    if type_id:
        if str(type_id) in blueprint_cache:
            type_name = blueprint_cache[str(type_id)]
        else:
            type_data = fetch_public_esi(f"/universe/types/{type_id}")
            if type_data:
                type_name = type_data.get('name', f"Blueprint {item_id}").replace(" Blueprint", "").strip()
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
                    location_name = struct_data.get('name', f"Citadel {location_id}")
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
                location_name = loc_data.get('name', f"Station {location_id}") if loc_data else f"Station {location_id}"
                location_cache[location_id_str] = location_name
                save_location_cache(location_cache)
    else:
        location_name = f"From {source.replace('_', ' ').title()}"
    
    # Construct title
    title = f"{type_name} {bp_type} {me}/{te} ({location_name}) – ID: {item_id}"

    post_data = {
        'title': title,
        'slug': f"blueprint-{item_id}",
        'status': 'publish',
        'meta': {
            '_eve_bp_item_id': item_id,
            '_eve_bp_type_id': blueprint_data.get('type_id'),
            '_eve_bp_location_id': blueprint_data.get('location_id'),
            '_eve_bp_location_name': location_name,
            '_eve_bp_quantity': blueprint_data.get('quantity', -1),
            '_eve_bp_me': blueprint_data.get('material_efficiency', 0),
            '_eve_bp_te': blueprint_data.get('time_efficiency', 0),
            '_eve_bp_runs': blueprint_data.get('runs', -1),
            '_eve_char_id': char_id,
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Add featured image from type icon (only for new blueprints)
    if not existing_post:
        type_id = blueprint_data.get('type_id')
        if type_id:
            image_url = fetch_type_icon(type_id, size=512)
            post_data['meta']['_thumbnail_external_url'] = image_url

    if existing_post:
        # Check if data has changed before updating
        existing_meta = existing_post.get('meta', {})
        existing_title = existing_post.get('title', {}).get('rendered', '')
        
        # Compare key fields
        needs_update = (
            existing_title != title or
            str(existing_meta.get('_eve_bp_location_name', '')) != str(location_name) or
            str(existing_meta.get('_eve_bp_me', 0)) != str(me) or
            str(existing_meta.get('_eve_bp_te', 0)) != str(te) or
            str(existing_meta.get('_eve_bp_quantity', -1)) != str(quantity) or
            str(existing_meta.get('_eve_bp_source', '')) != str(source)
        )
        
        if not needs_update:
            logger.info(f"Blueprint from {source}: {item_id} unchanged, skipping update")
            return
        
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint"
        response = requests.post(url, json=post_data, auth=get_wp_auth())
        
        # Cache the new post ID if creation was successful
        if response.status_code in [200, 201]:
            new_post = response.json()
            set_cached_wp_post_id(wp_post_id_cache, 'eve_blueprint', item_id, new_post['id'])

    if response.status_code in [200, 201]:
        logger.info(f"Updated blueprint from {source}: {item_id}")
    else:
        logger.error(f"Failed to update blueprint {item_id} from {source}: {response.status_code} - {response.text}")

def fetch_character_industry_jobs(char_id, access_token):
    """Fetch character industry jobs."""
    endpoint = f"/characters/{char_id}/industry/jobs/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_corporation_assets(corp_id, access_token):
    """Fetch corporation assets."""
    endpoint = f"/corporations/{corp_id}/assets/"
    return fetch_esi(endpoint, None, access_token)  # Corp endpoint doesn't need char_id

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

def update_contract_in_wp(contract_id, contract_data, for_corp=False, entity_id=None, access_token=None, blueprint_cache=None):
    """Update or create contract post in WordPress."""
    if blueprint_cache is None:
        blueprint_cache = load_blueprint_cache()
    
    slug = f"contract-{contract_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    # Fetch contract items if we have access token
    contract_items = None
    if access_token:
        if for_corp and entity_id:
            contract_items = fetch_corporation_contract_items(entity_id, contract_id, access_token)
        elif not for_corp and entity_id:
            contract_items = fetch_character_contract_items(entity_id, contract_id, access_token)

    # Generate descriptive title
    title = generate_contract_title(contract_data, contract_items, blueprint_cache)

    post_data = {
        'title': title,
        'slug': slug,
        'status': 'publish',
        'meta': {
            '_eve_contract_id': str(contract_id),
            '_eve_contract_type': contract_data.get('type'),
            '_eve_contract_status': contract_data.get('status'),
            '_eve_contract_issuer_id': str(contract_data.get('issuer_id')) if contract_data.get('issuer_id') is not None else None,
            '_eve_contract_issuer_corp_id': str(contract_data.get('issuer_corporation_id')) if contract_data.get('issuer_corporation_id') is not None else None,
            '_eve_contract_assignee_id': str(contract_data.get('assignee_id')) if contract_data.get('assignee_id') else None,
            '_eve_contract_acceptor_id': str(contract_data.get('acceptor_id')) if contract_data.get('acceptor_id') else None,
            '_eve_contract_start_location_id': str(contract_data.get('start_location_id')) if contract_data.get('start_location_id') else None,
            '_eve_contract_end_location_id': str(contract_data.get('end_location_id')) if contract_data.get('end_location_id') else None,
            '_eve_contract_date_issued': contract_data.get('date_issued'),
            '_eve_contract_date_expired': contract_data.get('date_expired'),
            '_eve_contract_date_accepted': contract_data.get('date_accepted'),
            '_eve_contract_date_completed': contract_data.get('date_completed'),
            '_eve_contract_price': str(contract_data.get('price')) if contract_data.get('price') is not None else None,
            '_eve_contract_reward': str(contract_data.get('reward')) if contract_data.get('reward') is not None else None,
            '_eve_contract_collateral': str(contract_data.get('collateral')) if contract_data.get('collateral') is not None else None,
            '_eve_contract_buyout': str(contract_data.get('buyout')) if contract_data.get('buyout') is not None else None,
            '_eve_contract_volume': str(contract_data.get('volume')) if contract_data.get('volume') is not None else None,
            '_eve_contract_days_to_complete': str(contract_data.get('days_to_complete')) if contract_data.get('days_to_complete') is not None else None,
            '_eve_contract_title': contract_data.get('title'),
            '_eve_contract_for_corp': str(for_corp).lower(),
            '_eve_contract_entity_id': str(entity_id),
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Remove null values from meta to avoid WordPress validation errors
    post_data['meta'] = {k: v for k, v in post_data['meta'].items() if v is not None}

    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None
    existing_meta = existing_post.get('meta', {}) if existing_post else {}

    # Add items data if available
    if contract_items:
        post_data['meta']['_eve_contract_items'] = json.dumps(contract_items)
        
        # Check for market competition on outstanding sell contracts
        if contract_data.get('status') == 'outstanding' and contract_data.get('type') == 'item_exchange':
            is_outbid, market_price = check_contract_market_competition(contract_data, contract_items)
            if is_outbid:
                post_data['meta']['_eve_contract_outbid'] = 'true'
                post_data['meta']['_eve_contract_market_price'] = str(market_price)
                logger.warning(f"Contract {contract_id} is outbid by market price: {market_price}")
                
                # Send alert if this is newly outbid
                was_outbid = existing_meta.get('_eve_contract_outbid') == 'true'
                if not was_outbid:
                    logger.warning(f"Contract {contract_id} is outbid by market price: {market_price}")
            else:
                post_data['meta']['_eve_contract_outbid'] = 'false'
                if '_eve_contract_market_price' in post_data['meta']:
                    del post_data['meta']['_eve_contract_market_price']
        else:
            # Not a sell contract or not outstanding - ensure outbid is false
            post_data['meta']['_eve_contract_outbid'] = 'false'
            if '_eve_contract_market_price' in post_data['meta']:
                del post_data['meta']['_eve_contract_market_price']
    else:
        # No contract items - ensure outbid is set to false
        post_data['meta']['_eve_contract_outbid'] = 'false'
        if '_eve_contract_market_price' in post_data['meta']:
            del post_data['meta']['_eve_contract_market_price']

    if existing_post:
        # Check if title changed before updating
        existing_title = existing_post.get('title', {}).get('rendered', '')
        
        # Compare key fields to see if update is needed
        needs_update = (
            existing_title != title or
            str(existing_meta.get('_eve_contract_status', '')) != str(contract_data.get('status', '')) or
            str(existing_meta.get('_eve_contract_items', '')) != str(json.dumps(contract_items) if contract_items else '') or
            str(existing_meta.get('_eve_contract_outbid', 'false')) != str(post_data['meta'].get('_eve_contract_outbid', 'false'))
        )
        
        if not needs_update:
            logger.info(f"Contract {contract_id} unchanged, skipping update")
            return
        
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        logger.info(f"Updated contract: {contract_id} - {title}")
    else:
        logger.error(f"Failed to update contract {contract_id}: {response.status_code} - {response.text}")

def fetch_market_orders(region_id, type_id):
    """Fetch market orders for a specific region and type."""
    endpoint = f"/markets/{region_id}/orders/?type_id={type_id}"
    return fetch_public_esi(endpoint)

def fetch_character_portrait(char_id):
    """Fetch character portrait URLs from ESI."""
    endpoint = f"/characters/{char_id}/portrait/"
    return fetch_public_esi(endpoint)

def fetch_corporation_logo(corp_id):
    """Fetch corporation logo URLs from ESI."""
    endpoint = f"/corporations/{corp_id}/logo/"
    return fetch_public_esi(endpoint)

def fetch_planet_details(char_id, planet_id, access_token):
    """Fetch detailed planet colony information."""
    endpoint = f"/characters/{char_id}/planets/{planet_id}/"
    return fetch_esi(endpoint, char_id, access_token) 
def refresh_token(refresh_token):
    """Refresh an access token."""
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    client_id = os.getenv('ESI_CLIENT_ID')
    client_secret = os.getenv('ESI_CLIENT_SECRET')
    response = requests.post('https://login.eveonline.com/v2/oauth/token', data=data, auth=(client_id, client_secret))
    if response.status_code == 200:
        token_data = response.json()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data['expires_in'])
        return {
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token', refresh_token),
            'expires_at': expires_at.isoformat()
        }
    else:
        logger.error(f"Failed to refresh token: {response.status_code} - {response.text}")
        return None

def check_contract_market_competition(contract_data, contract_items):
    """Check if a sell contract has been outbid by cheaper market orders in the same location."""
    if not contract_items or len(contract_items) != 1:
        return False, None  # Only check single item contracts
    
    contract_type = contract_data.get('type')
    if contract_type != 'item_exchange':
        return False, None  # Only check sell orders
    
    item = contract_items[0]
    type_id = item.get('type_id')
    quantity = item.get('quantity', 1)
    contract_price = contract_data.get('price', 0)
    
    if not type_id or quantity <= 0 or contract_price <= 0:
        return False, None
    
    price_per_item = contract_price / quantity
    
    # Get contract location
    start_location_id = contract_data.get('start_location_id')
    if not start_location_id:
        logger.warning(f"Contract {contract_data.get('contract_id')} missing start_location_id, skipping market check")
        return False, None
    
    # Get region_id from location
    region_id = None
    if start_location_id >= 1000000000000:  # Structure
        # For structures, we need to fetch structure info to get solar_system_id, then region
        struct_data = fetch_public_esi(f"/universe/structures/{start_location_id}")
        if struct_data:
            solar_system_id = struct_data.get('solar_system_id')
            if solar_system_id:
                system_data = fetch_public_esi(f"/universe/systems/{solar_system_id}")
                if system_data:
                    region_id = system_data.get('constellation_id')
                    if region_id:
                        constellation_data = fetch_public_esi(f"/universe/constellations/{region_id}")
                        if constellation_data:
                            region_id = constellation_data.get('region_id')
    else:  # Station
        station_data = fetch_public_esi(f"/universe/stations/{start_location_id}")
        if station_data:
            system_id = station_data.get('system_id')
            if system_id:
                system_data = fetch_public_esi(f"/universe/systems/{system_id}")
                if system_data:
                    constellation_id = system_data.get('constellation_id')
                    if constellation_id:
                        constellation_data = fetch_public_esi(f"/universe/constellations/{constellation_id}")
                        if constellation_data:
                            region_id = constellation_data.get('region_id')
    
    if not region_id:
        return False, None
    
    # Fetch market orders for this type in the region
    market_orders = fetch_market_orders(region_id, type_id)
    if not market_orders:
        return False, None
    
    # Filter to sell orders in the same location
    competing_orders = [
        order for order in market_orders
        if order.get('is_buy_order') == False and order.get('location_id') == start_location_id
    ]
    
    if not competing_orders:
        return False, None
    
    # Find the lowest sell price
    lowest_market_price = min(order.get('price', float('inf')) for order in competing_orders)
    
    if lowest_market_price < price_per_item:
        return True, lowest_market_price
    
    return False, None

def collect_corporation_members(tokens):
    """Collect all corporations and their member characters from authorized tokens."""
    corp_members = {}
    for char_id, token_data in tokens.items():
        try:
            expired = datetime.now(timezone.utc) > datetime.fromisoformat(token_data.get('expires_at', '2000-01-01T00:00:00+00:00'))
        except:
            expired = True
        if expired:
            new_token = refresh_token(token_data['refresh_token'])
            if new_token:
                token_data.update(new_token)
                save_tokens(tokens)
            else:
                logger.warning(f"Failed to refresh token for {token_data['name']}")
                continue

        access_token = token_data['access_token']
        char_name = token_data['name']

        # Fetch basic character data to get corporation
        char_data = fetch_character_data(char_id, access_token)
        if char_data:
            update_character_in_wp(char_id, char_data)
            corp_id = char_data.get('corporation_id')
            if corp_id:
                if corp_id not in corp_members:
                    corp_members[corp_id] = []
                corp_members[corp_id].append((char_id, access_token, char_name))

    return corp_members

def main():
    """Main data fetching routine."""
    # Load caches at the beginning
    blueprint_cache = load_blueprint_cache()
    location_cache = load_location_cache()
    structure_cache = load_structure_cache()
    failed_structures = load_failed_structures()
    wp_post_id_cache = load_wp_post_id_cache()

    tokens = load_tokens()
    if not tokens:
        logger.error("No authorized characters found. Run 'python esi_oauth.py authorize' first.")
        return

    # Collect all corporations and their member characters
    corp_members = collect_corporation_members(tokens)

    # Define allowed corporations and issuers for contract filtering
    allowed_corp_ids = {98092220}  # No Mercy Incorporated
    allowed_issuer_ids = set()
    for corp_id, members in corp_members.items():
        if corp_id == 98092220:  # No Mercy Incorporated
            for char_id, access_token, char_name in members:
                allowed_issuer_ids.add(char_id)

    # Clean up old posts with filtering
    cleanup_old_posts(allowed_corp_ids, allowed_issuer_ids)

    # Process each corporation with any available member token
    processed_corps = set()
    for corp_id, members in corp_members.items():
        if corp_id in processed_corps:
            continue

        # Process data for the corporation and its members
        process_corporation_data(corp_id, members, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures)

        processed_corps.add(corp_id)

    # Now process individual character data (skills, blueprints, etc.)
    for char_id, token_data in tokens.items():
        process_character_data(char_id, token_data, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures)

def process_corporation_data(corp_id, members, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures):
    """Process data for a single corporation and its members."""
    # For No Mercy Incorporated, prioritize Dr FiLiN's token (CEO)
    if corp_id == 98092220:  # No Mercy Incorporated
        # Find Dr FiLiN's token
        dr_filin_token = None
        dr_filin_char_id = None
        dr_filin_name = None
        for char_id, access_token, char_name in members:
            if char_name == 'Dr FiLiN':
                dr_filin_token = access_token
                dr_filin_char_id = char_id
                dr_filin_name = char_name
                break
        
        if dr_filin_token:
            logger.info(f"Using Dr FiLiN's CEO token for No Mercy Incorporated")
            corp_data = fetch_corporation_data(corp_id, dr_filin_token)
            if corp_data:
                successful_token = dr_filin_token
                successful_char_name = dr_filin_name
                successful_char_id = dr_filin_char_id
            else:
                logger.warning(f"Dr FiLiN's token failed for corporation {corp_id}, falling back to other members")
                successful_token = None
        else:
            logger.warning(f"Dr FiLiN's token not found for No Mercy Incorporated")
            successful_token = None
    else:
        successful_token = None
    
    # If we don't have a successful token yet (not No Mercy or Dr FiLiN failed), try each member
    if not successful_token:
        corp_data = None
        successful_char_name = None
        successful_char_id = None

        for char_id, access_token, char_name in members:
            # Skip Dr FiLiN if we already tried them for No Mercy
            if corp_id == 98092220 and char_name == 'Dr FiLiN':
                continue
                
            logger.info(f"Trying to fetch corporation data for corp {corp_id} using {char_name}'s token...")
            corp_data = fetch_corporation_data(corp_id, access_token)
            if corp_data:
                successful_token = access_token
                successful_char_name = char_name
                successful_char_id = char_id
                logger.info(f"Successfully fetched corporation data using {char_name}'s token")
                break
            else:
                logger.warning(f"Failed to fetch corporation data using {char_name}'s token (likely no access)")

    if not corp_data:
        return

    corp_name = corp_data.get('name', '')
    if corp_name.lower() not in ALLOWED_CORPORATIONS:
        logger.info(f"Skipping corporation: {corp_name} (only processing {ALLOWED_CORPORATIONS})")
        return

    update_corporation_in_wp(corp_id, corp_data)

    # Process corporation blueprints from various sources
    process_corporation_blueprints(corp_id, successful_token, successful_char_id, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures)

    # Process corporation contracts
    process_corporation_contracts(corp_id, successful_token, corp_data)

def process_corporation_blueprints(corp_id, access_token, char_id, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures):
    """Process all blueprint sources for a corporation."""
    logger.info(f"Fetching corporation blueprints for {corp_id}...")

    # From corporation blueprints endpoint
    corp_blueprints = fetch_corporation_blueprints(corp_id, access_token)
    if corp_blueprints:
        logger.info(f"Corporation blueprints: {len(corp_blueprints)} items")
        # Process blueprints in parallel
        process_blueprints_parallel(
            corp_blueprints,
            update_blueprint_in_wp,
            wp_post_id_cache,
            char_id,
            access_token,
            blueprint_cache,
            location_cache,
            structure_cache,
            failed_structures
        )

    # From corporation assets
    logger.info(f"Fetching corporation assets for {corp_id}...")
    if SKIP_CORPORATION_ASSETS:
        logger.info("Skipping corporation assets processing (SKIP_CORPORATION_ASSETS=true)")
    else:
        corp_assets = fetch_corporation_assets(corp_id, access_token)
        if corp_assets:
            logger.info(f"Fetched {len(corp_assets)} corporation assets")
            asset_blueprints = extract_blueprints_from_assets(corp_assets, 'corp', corp_id, access_token)
            if asset_blueprints:
                logger.info(f"Corporation asset blueprints: {len(asset_blueprints)} items")
                # Process blueprints in parallel
                process_blueprints_parallel(
                    asset_blueprints,
                    update_blueprint_from_asset_in_wp,
                    wp_post_id_cache,
                    char_id,
                    access_token,
                    blueprint_cache,
                    location_cache,
                    structure_cache,
                    failed_structures
                )
            else:
                logger.info("No blueprints found in corporation assets")
        else:
            logger.info("No corporation assets found or access denied")

    # From corporation industry jobs
    corp_industry_jobs = fetch_corporation_industry_jobs(corp_id, access_token)
    if corp_industry_jobs:
        job_blueprints = extract_blueprints_from_industry_jobs(corp_industry_jobs, 'corp', corp_id)
        if job_blueprints:
            logger.info(f"Corporation industry job blueprints: {len(job_blueprints)} items")
            # Process blueprints in parallel
            process_blueprints_parallel(
                job_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

    # From corporation contracts (blueprints already processed above)
    corp_contracts = fetch_corporation_contracts(corp_id, access_token)
    if corp_contracts:
        contract_blueprints = extract_blueprints_from_contracts(corp_contracts, 'corp', corp_id)
        if contract_blueprints:
            logger.info(f"Corporation contract blueprints: {len(contract_blueprints)} items")
            # Process blueprints in parallel
            process_blueprints_parallel(
                contract_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

def process_corporation_contracts(corp_id, access_token, corp_data):
    """Process contracts for a corporation."""
    corp_contracts = fetch_corporation_contracts(corp_id, access_token)
    if corp_contracts:
        logger.info(f"Corporation contracts for {corp_data.get('name', corp_id)}: {len(corp_contracts)} items")
        for contract in corp_contracts:
            contract_status = contract.get('status', '')
            if contract_status in ['finished', 'deleted']:
                # Skip finished/deleted contracts to improve performance
                continue
            elif contract_status == 'expired':
                logger.info(f"EXPIRED CORPORATION CONTRACT TO DELETE MANUALLY: {contract['contract_id']}")
            update_contract_in_wp(contract['contract_id'], contract, for_corp=True, entity_id=corp_id, access_token=access_token)

def process_character_data(char_id, token_data, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures):
    """Process data for a single character."""
    access_token = token_data['access_token']
    char_name = token_data['name']

    logger.info(f"Fetching additional data for {char_name}...")

    # Fetch skills
    skills = fetch_character_skills(char_id, access_token)
    if skills:
        # Update character with skills data
        update_character_skills_in_wp(char_id, skills)
        logger.info(f"Skills for {char_name}: {skills['total_sp']} SP")

    # Process character blueprints from all sources
    process_character_blueprints(char_id, access_token, char_name, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures)

    # Process character planets
    process_character_planets(char_id, access_token, char_name)

    # Process character contracts
    process_character_contracts(char_id, access_token, char_name, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures)

def process_character_blueprints(char_id, access_token, char_name, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures):
    """Process all blueprint sources for a character."""
    logger.info(f"Fetching blueprints for {char_name}...")

    # From character blueprints endpoint
    blueprints = fetch_character_blueprints(char_id, access_token)
    if blueprints:
        logger.info(f"Character blueprints: {len(blueprints)} items")
        # Process blueprints in parallel
        process_blueprints_parallel(
            blueprints,
            update_blueprint_in_wp,
            wp_post_id_cache,
            char_id,
            access_token,
            blueprint_cache,
            location_cache,
            structure_cache,
            failed_structures
        )

    # From character assets
    char_assets = fetch_character_assets(char_id, access_token)
    if char_assets:
        asset_blueprints = extract_blueprints_from_assets(char_assets, 'char', char_id, access_token)
        if asset_blueprints:
            logger.info(f"Character asset blueprints: {len(asset_blueprints)} items")
            # Process blueprints in parallel
            process_blueprints_parallel(
                asset_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

    # From character industry jobs (blueprints already processed above)
    jobs = fetch_character_industry_jobs(char_id, access_token)
    if jobs:
        logger.info(f"Industry jobs for {char_name}: {len(jobs)} active")
        job_blueprints = extract_blueprints_from_industry_jobs(jobs, 'char', char_id)
        if job_blueprints:
            logger.info(f"Character industry job blueprints: {len(job_blueprints)} items")
            # Process blueprints in parallel
            process_blueprints_parallel(
                job_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

        # Check for job completions and send alerts
        check_industry_job_completions(jobs, char_name)

def check_industry_job_completions(jobs, char_name):
    """Check for upcoming industry job completions and send alerts."""
    now = datetime.now(timezone.utc)
    upcoming_completions = []
    for job in jobs:
        if 'end_date' in job:
            end_date = datetime.fromisoformat(job['end_date'].replace('Z', '+00:00'))
            if now <= end_date <= now + timedelta(hours=24):
                upcoming_completions.append(job)

    if upcoming_completions:
        subject = f"EVE Alert: {len(upcoming_completions)} industry jobs ending soon for {char_name}"
        body = f"The following jobs will complete within 24 hours:\n\n"
        for job in upcoming_completions:
            body += f"- Job ID {job['job_id']}: {job.get('activity_id', 'Unknown')} ending {job['end_date']}\n"
        send_email(subject, body)

def process_character_planets(char_id, access_token, char_name):
    """Process planets for a character."""
    planets = fetch_character_planets(char_id, access_token)
    if planets:
        logger.info(f"Planets for {char_name}: {len(planets)} colonies")
        for planet in planets:
            planet_id = planet['planet_id']
            # Fetch details
            details = fetch_planet_details(char_id, planet_id, access_token)
            if details:
                planet.update(details)
                # Check for extraction completions
                check_planet_extraction_completions(details, char_name)
            update_planet_in_wp(planet_id, planet, char_id)

def check_planet_extraction_completions(planet_details, char_name):
    """Check for upcoming planet extraction completions and send alerts."""
    now = datetime.now(timezone.utc)
    upcoming_extractions = []
    for pin in planet_details.get('pins', []):
        if 'expiry_time' in pin:
            expiry = datetime.fromisoformat(pin['expiry_time'].replace('Z', '+00:00'))
            if now <= expiry <= now + timedelta(hours=24):
                upcoming_extractions.append(pin)
    if upcoming_extractions:
        subject = f"EVE Alert: {len(upcoming_extractions)} PI extractions ending soon for {char_name}"
        body = f"The following extractions will complete within 24 hours:\n\n"
        for pin in upcoming_extractions:
            body += f"- Pin {pin['pin_id']}: Type {pin.get('type_id', 'Unknown')} ending {pin['expiry_time']}\n"
        send_email(subject, body)

def process_character_contracts(char_id, access_token, char_name, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures):
    """Process contracts for a character."""
    char_contracts = fetch_character_contracts(char_id, access_token)
    if char_contracts:
        logger.info(f"Character contracts for {char_name}: {len(char_contracts)} items")
        contract_blueprints = extract_blueprints_from_contracts(char_contracts, 'char', char_id)
        if contract_blueprints:
            logger.info(f"Character contract blueprints: {len(contract_blueprints)} items")
            # Process blueprints in parallel
            process_blueprints_parallel(
                contract_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

        for contract in char_contracts:
            contract_status = contract.get('status', '')
            if contract_status in ['finished', 'deleted']:
                # Skip finished/deleted contracts to improve performance
                continue
            elif contract_status == 'expired':
                logger.info(f"EXPIRED CHARACTER CONTRACT TO DELETE MANUALLY: {contract['contract_id']}")
            update_contract_in_wp(contract['contract_id'], contract, for_corp=False, entity_id=char_id, access_token=access_token)

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

def update_corporation_in_wp(corp_id, corp_data):
    """Update or create corporation post in WordPress."""
    slug = f"corporation-{corp_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    post_data = {
        'title': corp_data['name'],
        'slug': slug,
        'status': 'publish',
        'meta': {
            '_eve_corp_id': corp_id,
            '_eve_corp_name': corp_data['name'],
            '_eve_corp_ticker': corp_data.get('ticker'),
            '_eve_corp_member_count': corp_data.get('member_count'),
            '_eve_corp_ceo_id': corp_data.get('ceo_id'),
            '_eve_corp_tax_rate': corp_data.get('tax_rate'),
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Add optional fields if they exist
    optional_fields = {
        '_eve_corp_alliance_id': corp_data.get('alliance_id'),
        '_eve_corp_date_founded': corp_data.get('date_founded'),
        '_eve_corp_creator_id': corp_data.get('creator_id'),
        '_eve_corp_home_station_id': corp_data.get('home_station_id'),
        '_eve_corp_shares': corp_data.get('shares'),
        '_eve_corp_description': corp_data.get('description'),
        '_eve_corp_url': corp_data.get('url'),
        '_eve_corp_war_eligible': corp_data.get('war_eligible'),
        '_eve_corp_faction_id': corp_data.get('faction_id')
    }
    for key, value in optional_fields.items():
        if value is not None:
            post_data['meta'][key] = value

    # Add featured image from corporation logo (only for new corporations)
    if not existing_post:
        logo_data = fetch_corporation_logo(corp_id)
        if logo_data and 'px256x256' in logo_data:
            post_data['meta']['_thumbnail_external_url'] = logo_data['px256x256']

    if existing_post:
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        logger.info(f"Updated corporation: {corp_data['name']}")
    else:
        logger.error(f"Failed to update corporation {corp_data['name']}: {response.status_code} - {response.text}")

def update_planet_in_wp(planet_id, planet_data, char_id):
    """Update or create planet post in WordPress."""
    slug = f"planet-{planet_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_planet?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    # Get planet name from ESI
    type_id = planet_data.get('type_id')
    if type_id:
        planet_type_data = fetch_public_esi(f"/universe/types/{type_id}")
        planet_name = planet_type_data.get('name', f"Planet {planet_id}") if planet_type_data else f"Planet {planet_id}"
    else:
        planet_name = f"Planet {planet_id}"

    post_data = {
        'title': f"{planet_name} - {char_id}",
        'slug': slug,
        'status': 'publish',
        'meta': {
            '_eve_planet_id': planet_id,
            '_eve_planet_type_id': planet_data.get('type_id'),
            '_eve_planet_name': planet_name,
            '_eve_planet_solar_system_id': planet_data.get('solar_system_id'),
            '_eve_char_id': char_id,
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Add colony details if available
    if 'pins' in planet_data:
        post_data['meta']['_eve_planet_pins'] = json.dumps(planet_data['pins'])
    if 'routes' in planet_data:
        post_data['meta']['_eve_planet_routes'] = json.dumps(planet_data['routes'])
    if 'links' in planet_data:
        post_data['meta']['_eve_planet_links'] = json.dumps(planet_data['links'])

    # Add featured image from planet type icon (only for new planets)
    if not existing_post:
        type_id = planet_data.get('type_id')
        if type_id:
            image_url = fetch_type_icon(type_id, size=512)
            post_data['meta']['_thumbnail_external_url'] = image_url

    if existing_post:
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_planet/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_planet"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        logger.info(f"Updated planet: {planet_id}")
    else:
        logger.error(f"Failed to update planet {planet_id}: {response.status_code} - {response.text}")

def save_failed_structures(failed_structures):
    """Save failed structures cache."""
    save_cache(FAILED_STRUCTURES_FILE, failed_structures)

def cleanup_old_posts(allowed_corp_ids, allowed_issuer_ids):
    """Clean up posts that don't match our criteria."""
    logger.info("Starting cleanup of old posts...")

    # Clean up contract posts (delete finished/deleted contracts and those not from allowed corps/issuers)
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract", auth=get_wp_auth(), params={'per_page': WP_PER_PAGE})
    if response.status_code == 200:
        contracts = response.json()
        for contract in contracts:
            meta = contract.get('meta', {})
            status = meta.get('_eve_contract_status')
            issuer_corp_id = meta.get('_eve_contract_issuer_corp_id')
            issuer_id = meta.get('_eve_contract_issuer_id')
            contract_id = meta.get('_eve_contract_id')
            
            should_delete = False
            if issuer_corp_id and int(issuer_corp_id) not in allowed_corp_ids and issuer_id and int(issuer_id) not in allowed_issuer_ids:
                should_delete = True
                logger.info(f"Deleting contract from unauthorized issuer: {contract_id}")
            elif status == 'expired':
                # List expired contracts for manual deletion
                title = contract.get('title', {}).get('rendered', f'Contract {contract_id}')
                logger.info(f"EXPIRED CONTRACT TO DELETE MANUALLY: {title} (ID: {contract_id})")
            
            if should_delete:
                delete_wp_post('eve_contract', contract['id'])

    # Clean up blueprint posts (only keep those from No Mercy incorporated or characters)
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint", auth=get_wp_auth(), params={'per_page': WP_PER_PAGE})
    if response.status_code == 200:
        blueprints = response.json()
        for bp in blueprints:
            meta = bp.get('meta', {})
            quantity = meta.get('_eve_bp_quantity', -1)
            owner_id = meta.get('_eve_bp_owner_id')
            source = meta.get('_eve_bp_source', '')
            char_id = meta.get('_eve_char_id')
            
            # Remove BPCs (we only want to track BPOs now)
            if quantity != -1:
                bp_id = meta.get('_eve_bp_item_id')
                logger.info(f"Deleting BPC (quantity={quantity}): {bp_id}")
                delete_wp_post('eve_blueprint', bp['id'])
                continue
            
            # If it's from a corporation, check if it's No Mercy incorporated
            if owner_id and source.startswith('corp_'):
                # We need to check if this corp_id belongs to No Mercy incorporated
                corp_response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation?meta_key=_eve_corp_id&meta_value={owner_id}", auth=get_wp_auth())
                if corp_response.status_code == 200:
                    corp_posts = corp_response.json()
                    if not corp_posts:  # Corporation not found in our records
                        bp_id = bp.get('meta', {}).get('_eve_bp_item_id')
                        logger.info(f"Deleting blueprint from unknown corporation: {bp_id}")
                        delete_wp_post('eve_blueprint', bp['id'])
                    else:
                        corp_name = corp_posts[0].get('title', {}).get('rendered', '')
                        if corp_name.lower() != 'no mercy incorporated':
                            bp_id = bp.get('meta', {}).get('_eve_bp_item_id')
                            logger.info(f"Deleting blueprint from {corp_name}: {bp_id}")
                            delete_wp_post('eve_blueprint', bp['id'])
            # If it's from character assets/industry jobs and we don't have a char_id, it might be orphaned
            elif not char_id and not owner_id:
                # These are from the direct blueprint endpoints - check if they're corporation blueprints
                # For now, keep them as they come from authenticated sources
                pass

    logger.info("Cleanup completed.")

if __name__ == "__main__":
    main()