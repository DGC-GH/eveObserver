#!/usr/bin/env python3
"""
EVE Observer Data Fetcher
Fetches data from EVE ESI API and stores in WordPress database via REST API.
"""

import os
import json
import requests
from datetime import datetime, timedelta
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

def update_character_in_wp(char_id, char_data):
    """Update or create character post in WordPress."""
    # Check if post exists
    search_url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_character?meta_key=_eve_char_id&meta_value={char_id}"
    response = requests.get(search_url, auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []

    post_data = {
        'title': char_data['name'],
        'status': 'publish',
        'meta': {
            '_eve_char_id': char_id,
            '_eve_char_name': char_data['name'],
            '_eve_corporation_id': char_data.get('corporation_id'),
            '_eve_alliance_id': char_data.get('alliance_id'),
            '_eve_birthday': char_data.get('birthday'),
            '_eve_gender': char_data.get('gender'),
            '_eve_race_id': char_data.get('race_id'),
            '_eve_bloodline_id': char_data.get('bloodline_id'),
            '_eve_ancestry_id': char_data.get('ancestry_id'),
            '_eve_security_status': char_data.get('security_status'),
            '_eve_last_updated': datetime.utcnow().isoformat()
        }
    }

    if existing_posts:
        # Update existing
        post_id = existing_posts[0]['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_character/{post_id}"
        response = requests.post(url, json=post_data, auth=get_wp_auth())
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

        # Fetch industry jobs
        jobs = fetch_character_industry_jobs(char_id, access_token)
        if jobs:
            print(f"Industry jobs for {char_name}: {len(jobs)} active")
            # Check for job completions
            now = datetime.utcnow()
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

        # Fetch corporation data if available
        corp_id = char_data.get('corporation_id')
        if corp_id:
            print(f"Fetching corporation data for corp ID: {corp_id}")

            # Fetch corp contracts
            corp_contracts = fetch_corporation_contracts(corp_id, access_token)
            if corp_contracts:
                print(f"Corporation contracts: {len(corp_contracts)} items")

            # Fetch corp assets
            corp_assets = fetch_corporation_assets(corp_id, access_token)
            if corp_assets:
                print(f"Corporation assets: {len(corp_assets)} items")

    # Fetch sample market data
    print("Fetching sample market data...")
    market_data = fetch_market_orders(10000002, 34)  # Tritanium in The Forge
    if market_data:
        print(f"Market orders for Tritanium: {len(market_data)} orders")

    print("Data fetch complete.")

if __name__ == '__main__':
    main()