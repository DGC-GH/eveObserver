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

load_dotenv()

# Configuration
WP_BASE_URL = os.getenv('WP_URL', 'https://your-wordpress-site.com')
WP_USERNAME = os.getenv('WP_USERNAME')
WP_APP_PASSWORD = os.getenv('WP_APP_PASSWORD')

# Email configuration
EMAIL_SMTP_SERVER = os.getenv('EMAIL_SMTP_SERVER')
EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', 587))
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_FROM = os.getenv('EMAIL_FROM')
EMAIL_TO = os.getenv('EMAIL_TO')

ESI_BASE_URL = 'https://esi.evetech.net/latest'

# Files
TOKENS_FILE = 'esi_tokens.json'

def load_tokens():
    """Load stored tokens."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return {}

def send_email(subject, body):
    """Send an email alert."""
    if not all([EMAIL_SMTP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO]):
        print("Email configuration incomplete, skipping alert.")
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
        print(f"Alert email sent: {subject}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def fetch_public_esi(endpoint):
    """Fetch data from ESI API (public endpoints, no auth) with rate limiting."""
    import time

    url = f"{ESI_BASE_URL}{endpoint}"

    while True:  # Retry loop for rate limiting
        response = requests.get(url)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:  # Rate limited
            # Check for X-ESI-Error-Limit-Remain header
            error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
            error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

            if error_limit_reset:
                wait_time = int(error_limit_reset) + 1  # Add 1 second buffer
                print(f"Rate limited on public endpoint. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                # Fallback: wait 60 seconds if no reset header
                print("Rate limited on public endpoint. Waiting 60 seconds...")
                time.sleep(60)
                continue
        elif response.status_code == 420:  # Error limited
            error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
            error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

            if error_limit_reset:
                wait_time = int(error_limit_reset) + 1
                print(f"Error limited on public endpoint. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                print("Error limited on public endpoint. Waiting 60 seconds...")
                time.sleep(60)
                continue
        else:
            print(f"ESI API error for {endpoint}: {response.status_code} - {response.text}")
            return None

def fetch_esi(endpoint, char_id, access_token):
    """Fetch data from ESI API with rate limiting."""
    import time

    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {'Authorization': f'Bearer {access_token}'}

    while True:  # Retry loop for rate limiting
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:  # Rate limited
            # Check for X-ESI-Error-Limit-Remain header
            error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
            error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

            if error_limit_reset:
                wait_time = int(error_limit_reset) + 1  # Add 1 second buffer
                print(f"Rate limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                # Fallback: wait 60 seconds if no reset header
                print("Rate limited. Waiting 60 seconds...")
                time.sleep(60)
                continue
        elif response.status_code == 420:  # Error limited
            error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
            error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

            if error_limit_reset:
                wait_time = int(error_limit_reset) + 1
                print(f"Error limited. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                print("Error limited. Waiting 60 seconds...")
                time.sleep(60)
                continue
        else:
            print(f"ESI API error for {endpoint}: {response.status_code} - {response.text}")
            return None

def get_wp_auth():
    """Get WordPress authentication tuple."""
    return (WP_USERNAME, WP_APP_PASSWORD)

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
        print(f"Updated character: {char_data['name']}")
    else:
        print(f"Failed to update character {char_data['name']}: {response.status_code} - {response.text}")

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
            print(f"Updated skills for character {char_id}")
        else:
            print(f"Failed to update skills for character {char_id}: {response.status_code} - {response.text}")

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

def update_blueprint_in_wp(item_id, blueprint_data, char_id, access_token):
    """Update or create blueprint post in WordPress."""
    slug = f"blueprint-{item_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    # Get blueprint name and details
    type_id = blueprint_data.get('type_id')
    me = blueprint_data.get('material_efficiency', 0)
    te = blueprint_data.get('time_efficiency', 0)
    location_id = blueprint_data.get('location_id')
    quantity = blueprint_data.get('quantity', -1)
    
    if type_id:
        type_data = fetch_public_esi(f"/universe/types/{type_id}")
        if type_data:
            type_name = type_data.get('name', f"Blueprint {item_id}").replace(" Blueprint", "").strip()
        else:
            type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()
    else:
        type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()
    
    # Determine BPO or BPC
    bp_type = "BPO" if quantity == -1 else "BPC"
    
    # Get location name
    if location_id:
        if location_id >= 1000000000000:  # Structures (citadels, etc.) - try auth fetch
            struct_data = fetch_esi(f"/universe/structures/{location_id}", char_id, access_token)
            location_name = struct_data.get('name', f"Citadel {location_id}") if struct_data else f"Citadel {location_id}"
        else:  # Stations - public
            loc_data = fetch_public_esi(f"/universe/stations/{location_id}")
            location_name = loc_data.get('name', f"Station {location_id}") if loc_data else f"Station {location_id}"
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

    if existing_post:
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        print(f"Updated blueprint: {item_id}")
    else:
        print(f"Failed to update blueprint {item_id}: {response.status_code} - {response.text}")

def fetch_character_assets(char_id, access_token):
    """Fetch character assets."""
    endpoint = f"/characters/{char_id}/assets/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_corporation_blueprints(corp_id, access_token):
    """Fetch corporation blueprints."""
    endpoint = f"/corporations/{corp_id}/blueprints/"
    return fetch_esi(endpoint, corp_id, access_token)

def fetch_corporation_industry_jobs(corp_id, access_token):
    """Fetch corporation industry jobs."""
    endpoint = f"/corporations/{corp_id}/industry/jobs/"
    return fetch_esi(endpoint, corp_id, access_token)

def extract_blueprints_from_assets(assets_data, owner_type, owner_id, access_token):
    """Extract blueprint information from assets data."""
    blueprints = []
    
    def process_items(items, location_id):
        for item in items:
            # Check if this is a blueprint (type_id corresponds to a blueprint)
            type_id = item.get('type_id')
            if type_id:
                # Get type information to check if it's a blueprint
                type_data = fetch_public_esi(f"/universe/types/{type_id}")
                if type_data and 'Blueprint' in type_data.get('name', ''):
                    # This is a blueprint
                    blueprint_info = {
                        'item_id': item.get('item_id'),
                        'type_id': type_id,
                        'location_id': location_id,
                        'quantity': item.get('quantity', 1),
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
    
    return blueprints

def extract_blueprints_from_industry_jobs(jobs_data, owner_type, owner_id):
    """Extract blueprint information from industry jobs."""
    blueprints = []
    
    for job in jobs_data:
        blueprint_id = job.get('blueprint_id')
        blueprint_type_id = job.get('blueprint_type_id')
        if blueprint_id and blueprint_type_id:
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
    blueprints = []
    
    for contract in contracts_data:
        if 'items' in contract:
            for item in contract['items']:
                type_id = item.get('type_id')
                if type_id:
                    # Get type information to check if it's a blueprint
                    type_data = fetch_public_esi(f"/universe/types/{type_id}")
                    if type_data and 'Blueprint' in type_data.get('name', ''):
                        blueprint_info = {
                            'item_id': item.get('item_id', type_id),  # Contracts may not have item_id
                            'type_id': type_id,
                            'location_id': None,  # Contracts don't specify location
                            'quantity': item.get('quantity', 1),
                            'material_efficiency': 0,  # Contract items don't provide ME/TE
                            'time_efficiency': 0,
                            'runs': -1,
                            'source': f"{owner_type}_contract_{contract.get('contract_id')}",
                            'owner_id': owner_id
                        }
                        blueprints.append(blueprint_info)
    
    return blueprints

def update_blueprint_from_asset_in_wp(blueprint_data, access_token):
    """Update or create blueprint post from asset/industry/contract data."""
    item_id = blueprint_data['item_id']
    owner_id = blueprint_data['owner_id']
    source = blueprint_data['source']
    
    slug = f"blueprint-{item_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    # Get blueprint name and details
    type_id = blueprint_data.get('type_id')
    me = blueprint_data.get('material_efficiency', 0)
    te = blueprint_data.get('time_efficiency', 0)
    location_id = blueprint_data.get('location_id')
    quantity = blueprint_data.get('quantity', -1)
    
    if type_id:
        type_data = fetch_public_esi(f"/universe/types/{type_id}")
        if type_data:
            type_name = type_data.get('name', f"Blueprint {item_id}").replace(" Blueprint", "").strip()
        else:
            type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()
    else:
        type_name = f"Blueprint {item_id}".replace(" Blueprint", "").strip()
    
    # Determine BPO or BPC
    bp_type = "BPO" if quantity == -1 else "BPC"
    
    # Get location name
    if location_id:
        if location_id >= 1000000000000:  # Structures (citadels, etc.) - try auth fetch
            struct_data = fetch_esi(f"/universe/structures/{location_id}", owner_id if source.startswith('char') else None, access_token)
            location_name = struct_data.get('name', f"Citadel {location_id}") if struct_data else f"Citadel {location_id}"
        else:  # Stations - public
            loc_data = fetch_public_esi(f"/universe/stations/{location_id}")
            location_name = loc_data.get('name', f"Station {location_id}") if loc_data else f"Station {location_id}"
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
            '_eve_bp_source': source,
            '_eve_bp_owner_id': owner_id,
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    if existing_post:
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        print(f"Updated blueprint from {source}: {item_id}")
    else:
        print(f"Failed to update blueprint {item_id} from {source}: {response.status_code} - {response.text}")

def fetch_character_industry_jobs(char_id, access_token):
    """Fetch character industry jobs."""
    endpoint = f"/characters/{char_id}/industry/jobs/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_character_contracts(char_id, access_token):
    """Fetch character contracts."""
    endpoint = f"/characters/{char_id}/contracts/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_corporation_contracts(corp_id, access_token):
    """Fetch corporation contracts."""
    endpoint = f"/corporations/{corp_id}/contracts/"
    return fetch_esi(endpoint, corp_id, access_token)

def fetch_corporation_assets(corp_id, access_token):
    """Fetch corporation assets."""
    endpoint = f"/corporations/{corp_id}/assets/"
    return fetch_esi(endpoint, corp_id, access_token)

def update_corporation_in_wp(corp_id, corp_data):
    """Update or create corporation post in WordPress."""
    slug = f"corporation-{corp_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    post_data = {
        'title': corp_data.get('name', f"Corporation {corp_id}"),
        'slug': slug,
        'status': 'publish',
        'meta': {
            '_eve_corp_id': corp_id,
            '_eve_corp_name': corp_data.get('name'),
            '_eve_corp_ticker': corp_data.get('ticker'),
            '_eve_corp_member_count': corp_data.get('member_count'),
            '_eve_corp_ceo_id': corp_data.get('ceo_id'),
            '_eve_corp_alliance_id': corp_data.get('alliance_id'),
            '_eve_corp_tax_rate': corp_data.get('tax_rate'),
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

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
        print(f"Updated corporation: {corp_data.get('name', corp_id)}")
    else:
        print(f"Failed to update corporation {corp_id}: {response.status_code} - {response.text}")

def fetch_planet_details(char_id, planet_id, access_token):
    """Fetch detailed planet information including pins."""
    endpoint = f"/characters/{char_id}/planets/{planet_id}/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_corporation_data(corp_id, access_token):
    """Fetch corporation data from ESI."""
    endpoint = f"/corporations/{corp_id}/"
    return fetch_esi(endpoint, None, access_token)  # No char_id needed for corp data

def update_planet_in_wp(planet_id, planet_data, char_id):
    """Update or create planet post in WordPress."""
    slug = f"planet-{planet_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_planet?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    # Get planet name
    planet_info = fetch_public_esi(f"/universe/planets/{planet_id}")
    if planet_info:
        title = planet_info.get('name', f"Planet {planet_id}")
    else:
        title = f"Planet {planet_id}"

    post_data = {
        'title': title,
        'slug': f"planet-{planet_id}",
        'status': 'publish',
        'meta': {
            '_eve_planet_id': planet_id,
            '_eve_planet_type': planet_data.get('planet_type'),
            '_eve_planet_solar_system_id': planet_data.get('solar_system_id'),
            '_eve_planet_upgrade_level': planet_data.get('upgrade_level'),
            '_eve_char_id': char_id,
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    if 'pins' in planet_data:
        post_data['meta']['_eve_planet_pins_data'] = json.dumps(planet_data['pins'])

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
        print(f"Updated planet: {planet_id}")
    else:
        print(f"Failed to update planet {planet_id}: {response.status_code} - {response.text}")

def update_contract_in_wp(contract_id, contract_data, for_corp=False, entity_id=None):
    """Update or create contract post in WordPress."""
    slug = f"contract-{contract_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    # Get contract type name
    contract_type = contract_data.get('type', 'unknown')
    type_names = {
        'item_exchange': 'Item Exchange',
        'auction': 'Auction',
        'courier': 'Courier',
        'loan': 'Loan'
    }
    type_name = type_names.get(contract_type, contract_type.title())

    # Get status
    status = contract_data.get('status', 'unknown').title()

    # Get issuer/assignee names if available
    issuer_name = contract_data.get('issuer_corporation_id', 'Unknown')
    assignee_name = contract_data.get('assignee_id', 'Unknown')

    # Construct title
    title = f"Contract {contract_id} - {type_name} ({status})"

    post_data = {
        'title': title,
        'slug': slug,
        'status': 'publish',
        'meta': {
            '_eve_contract_id': contract_id,
            '_eve_contract_type': contract_data.get('type'),
            '_eve_contract_status': contract_data.get('status'),
            '_eve_contract_issuer_id': contract_data.get('issuer_id'),
            '_eve_contract_issuer_corp_id': contract_data.get('issuer_corporation_id'),
            '_eve_contract_assignee_id': contract_data.get('assignee_id'),
            '_eve_contract_acceptor_id': contract_data.get('acceptor_id'),
            '_eve_contract_date_issued': contract_data.get('date_issued'),
            '_eve_contract_date_expired': contract_data.get('date_expired'),
            '_eve_contract_date_accepted': contract_data.get('date_accepted'),
            '_eve_contract_date_completed': contract_data.get('date_completed'),
            '_eve_contract_price': contract_data.get('price'),
            '_eve_contract_reward': contract_data.get('reward'),
            '_eve_contract_collateral': contract_data.get('collateral'),
            '_eve_contract_buyout': contract_data.get('buyout'),
            '_eve_contract_volume': contract_data.get('volume'),
            '_eve_contract_days_to_complete': contract_data.get('days_to_complete'),
            '_eve_contract_title': contract_data.get('title'),
            '_eve_contract_for_corp': for_corp,
            '_eve_contract_entity_id': entity_id,
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Add items data if available
    if 'items' in contract_data:
        post_data['meta']['_eve_contract_items'] = json.dumps(contract_data['items'])

    if existing_post:
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        print(f"Updated contract: {contract_id}")
    else:
        print(f"Failed to update contract {contract_id}: {response.status_code} - {response.text}")

def save_tokens(tokens):
    """Save tokens to file."""
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f)

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
        print(f"Failed to refresh token: {response.status_code} - {response.text}")
        return None

def fetch_market_orders(region_id, type_id):
    """Fetch market orders for a type in a region with rate limiting."""
    import time

    endpoint = f"/markets/{region_id}/orders/?type_id={type_id}"
    # Note: market orders don't require auth, but rate limited
    url = f"{ESI_BASE_URL}{endpoint}"

    while True:  # Retry loop for rate limiting
        response = requests.get(url)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:  # Rate limited
            # Check for X-ESI-Error-Limit-Remain header
            error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
            error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

            if error_limit_reset:
                wait_time = int(error_limit_reset) + 1  # Add 1 second buffer
                print(f"Rate limited on market orders. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                # Fallback: wait 60 seconds if no reset header
                print("Rate limited on market orders. Waiting 60 seconds...")
                time.sleep(60)
                continue
        elif response.status_code == 420:  # Error limited
            error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
            error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

            if error_limit_reset:
                wait_time = int(error_limit_reset) + 1
                print(f"Error limited on market orders. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                print("Error limited on market orders. Waiting 60 seconds...")
                time.sleep(60)
                continue
        else:
            print(f"ESI API error for market orders: {response.status_code} - {response.text}")
            return None

def main():
    """Main data fetching routine."""
    tokens = load_tokens()
    if not tokens:
        print("No authorized characters found. Run 'python esi_oauth.py authorize' first.")
        return

    # Collect all corporations and their member characters
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
                print(f"Failed to refresh token for {token_data['name']}")
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

    # Process each corporation with any available member token
    processed_corps = set()
    for corp_id, members in corp_members.items():
        if corp_id in processed_corps:
            continue

        # Try each member until we successfully fetch corp data
        corp_data = None
        successful_token = None
        successful_char_name = None

        for char_id, access_token, char_name in members:
            print(f"Trying to fetch corporation data for corp {corp_id} using {char_name}'s token...")
            corp_data = fetch_corporation_data(corp_id, access_token)
            if corp_data:
                successful_token = access_token
                successful_char_name = char_name
                print(f"Successfully fetched corporation data using {char_name}'s token")
                break
            else:
                print(f"Failed to fetch corporation data using {char_name}'s token (likely no access)")

        if corp_data:
            update_corporation_in_wp(corp_id, corp_data)
            processed_corps.add(corp_id)

            # Fetch corporation blueprints from various sources
            print(f"Fetching corporation blueprints for {corp_data.get('name', corp_id)}...")
            
            # From corporation blueprints endpoint
            corp_blueprints = fetch_corporation_blueprints(corp_id, successful_token)
            if corp_blueprints:
                print(f"Corporation blueprints: {len(corp_blueprints)} items")
                for bp in corp_blueprints:
                    update_blueprint_in_wp(bp['item_id'], bp, successful_char_name, successful_token)
            
            # From corporation assets
            corp_assets = fetch_corporation_assets(corp_id, successful_token)
            if corp_assets:
                asset_blueprints = extract_blueprints_from_assets(corp_assets, 'corp', corp_id, successful_token)
                if asset_blueprints:
                    print(f"Corporation asset blueprints: {len(asset_blueprints)} items")
                    for bp in asset_blueprints:
                        update_blueprint_from_asset_in_wp(bp, successful_token)
            
            # From corporation industry jobs
            corp_industry_jobs = fetch_corporation_industry_jobs(corp_id, successful_token)
            if corp_industry_jobs:
                job_blueprints = extract_blueprints_from_industry_jobs(corp_industry_jobs, 'corp', corp_id)
                if job_blueprints:
                    print(f"Corporation industry job blueprints: {len(job_blueprints)} items")
                    for bp in job_blueprints:
                        update_blueprint_from_asset_in_wp(bp, successful_token)
            
            # From corporation contracts (blueprints already processed above)
            corp_contracts = fetch_corporation_contracts(corp_id, successful_token)
            if corp_contracts:
                print(f"Corporation contracts for {corp_data.get('name', corp_id)}: {len(corp_contracts)} items")
                contract_blueprints = extract_blueprints_from_contracts(corp_contracts, 'corp', corp_id)
                if contract_blueprints:
                    print(f"Corporation contract blueprints: {len(contract_blueprints)} items")
                    for bp in contract_blueprints:
                        update_blueprint_from_asset_in_wp(bp, successful_token)
                
                for contract in corp_contracts:
                    update_contract_in_wp(contract['contract_id'], contract, for_corp=True, entity_id=corp_id)

    # Now process individual character data (skills, blueprints, etc.)
    for char_id, token_data in tokens.items():
        access_token = token_data['access_token']
        char_name = token_data['name']

        print(f"Fetching additional data for {char_name}...")

        # Fetch skills
        skills = fetch_character_skills(char_id, access_token)
        if skills:
            # Update character with skills data
            update_character_skills_in_wp(char_id, skills)
            print(f"Skills for {char_name}: {skills['total_sp']} SP")

        # Fetch blueprints from all sources
        print(f"Fetching blueprints for {char_name}...")
        
        # From character blueprints endpoint
        blueprints = fetch_character_blueprints(char_id, access_token)
        if blueprints:
            print(f"Character blueprints: {len(blueprints)} items")
            for bp in blueprints:
                update_blueprint_in_wp(bp['item_id'], bp, char_id, access_token)
        
        # From character assets
        char_assets = fetch_character_assets(char_id, access_token)
        if char_assets:
            asset_blueprints = extract_blueprints_from_assets(char_assets, 'char', char_id, access_token)
            if asset_blueprints:
                print(f"Character asset blueprints: {len(asset_blueprints)} items")
                for bp in asset_blueprints:
                    update_blueprint_from_asset_in_wp(bp, access_token)
        
        # From character industry jobs (blueprints already processed above)
        jobs = fetch_character_industry_jobs(char_id, access_token)
        if jobs:
            print(f"Industry jobs for {char_name}: {len(jobs)} active")
            job_blueprints = extract_blueprints_from_industry_jobs(jobs, 'char', char_id)
            if job_blueprints:
                print(f"Character industry job blueprints: {len(job_blueprints)} items")
                for bp in job_blueprints:
                    update_blueprint_from_asset_in_wp(bp, access_token)
            
            # Check for job completions
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

        # Fetch planets
        planets = fetch_character_planets(char_id, access_token)
        if planets:
            print(f"Planets for {char_name}: {len(planets)} colonies")
            for planet in planets:
                planet_id = planet['planet_id']
                # Fetch details
                details = fetch_planet_details(char_id, planet_id, access_token)
                if details:
                    planet.update(details)
                    # Check for extraction completions
                    now = datetime.now(timezone.utc)
                    upcoming_extractions = []
                    for pin in details.get('pins', []):
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
                update_planet_in_wp(planet_id, planet, char_id)

        # Fetch character contracts (blueprints already processed above)
        char_contracts = fetch_character_contracts(char_id, access_token)
        if char_contracts:
            print(f"Character contracts for {char_name}: {len(char_contracts)} items")
            contract_blueprints = extract_blueprints_from_contracts(char_contracts, 'char', char_id)
            if contract_blueprints:
                print(f"Character contract blueprints: {len(contract_blueprints)} items")
                for bp in contract_blueprints:
                    update_blueprint_from_asset_in_wp(bp, access_token)
            
            for contract in char_contracts:
                update_contract_in_wp(contract['contract_id'], contract, for_corp=False, entity_id=char_id)

if __name__ == '__main__':
    main()