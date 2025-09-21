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
    """Fetch data from ESI API (public endpoints, no auth)."""
    url = f"{ESI_BASE_URL}{endpoint}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"ESI API error for {endpoint}: {response.status_code} - {response.text}")
        return None

def fetch_esi(endpoint, char_id, access_token):
    """Fetch data from ESI API."""
    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
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

def update_blueprint_in_wp(item_id, blueprint_data, char_id):
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
        if location_id >= 1000000000000:  # Structures (citadels, etc.) - require auth, so use generic name
            location_name = f"Citadel {location_id}"
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

def fetch_character_industry_jobs(char_id, access_token):
    """Fetch character industry jobs."""
    endpoint = f"/characters/{char_id}/industry/jobs/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_character_planets(char_id, access_token):
    """Fetch character planets."""
    endpoint = f"/characters/{char_id}/planets/"
    return fetch_esi(endpoint, char_id, access_token)

def fetch_corporation_contracts(corp_id, access_token):
    """Fetch corporation contracts."""
    endpoint = f"/corporations/{corp_id}/contracts/"
    return fetch_esi(endpoint, corp_id, access_token)

def fetch_corporation_assets(corp_id, access_token):
    """Fetch corporation assets."""
    endpoint = f"/corporations/{corp_id}/assets/"
    return fetch_esi(endpoint, corp_id, access_token)

def fetch_planet_details(char_id, planet_id, access_token):
    """Fetch detailed planet information including pins."""
    endpoint = f"/characters/{char_id}/planets/{planet_id}/"
    return fetch_esi(endpoint, char_id, access_token)

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
    """Fetch market orders for a type in a region."""
    endpoint = f"/markets/{region_id}/orders/?type_id={type_id}"
    # Note: market orders don't require auth, but rate limited
    url = f"{ESI_BASE_URL}{endpoint}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"ESI API error for market orders: {response.status_code} - {response.text}")
        return None

def main():
    """Main data fetching routine."""
    tokens = load_tokens()
    if not tokens:
        print("No authorized characters found. Run 'python esi_oauth.py authorize' first.")
        return

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

        print(f"Fetching data for {char_name}...")

        # Fetch basic character data
        char_data = fetch_character_data(char_id, access_token)
        if char_data:
            update_character_in_wp(char_id, char_data)

        # Fetch skills
        skills = fetch_character_skills(char_id, access_token)
        if skills:
            # Store skills in meta or ACF (for now, just print)
            print(f"Skills for {char_name}: {skills['total_sp']} SP")

        # Fetch blueprints
        blueprints = fetch_character_blueprints(char_id, access_token)
        if blueprints:
            print(f"Blueprints for {char_name}: {len(blueprints)} items")
            for bp in blueprints:
                update_blueprint_in_wp(bp['item_id'], bp, char_id)

        # Fetch industry jobs
        jobs = fetch_character_industry_jobs(char_id, access_token)
        if jobs:
            print(f"Industry jobs for {char_name}: {len(jobs)} active")
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

        # Fetch corporation data if available
        # corp_id = char_data.get('corporation_id') if char_data else None
        # if corp_id:
        #     print(f"Fetching corporation data for corp ID: {corp_id}")

        #     # Fetch corp contracts
        #     corp_contracts = fetch_corporation_contracts(corp_id, access_token)
        #     if corp_contracts:
        #         print(f"Corporation contracts: {len(corp_contracts)} items")

        #     # Fetch corp assets
        #     corp_assets = fetch_corporation_assets(corp_id, access_token)
        #     if corp_assets:
        #         print(f"Corporation assets: {len(corp_assets)} items")

    # Fetch sample market data
    print("Fetching sample market data...")
    market_data = fetch_market_orders(10000002, 34)  # Tritanium in The Forge
    if market_data:
        print(f"Market orders for Tritanium: {len(market_data)} orders")

    print("Data fetch complete.")

if __name__ == '__main__':
    main()