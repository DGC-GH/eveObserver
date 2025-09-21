#!/usr/bin/env python3
"""
EVE ESI OAuth Script for EVE Observer
Handles OAuth flow to obtain access and refresh tokens for EVE characters.
"""

import os
import json
import secrets
import webbrowser
from urllib.parse import urlencode, parse_qs
import requests
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ESI OAuth endpoints
AUTHORIZATION_BASE_URL = 'https://login.eveonline.com/v2/oauth/authorize'
TOKEN_URL = 'https://login.eveonline.com/v2/oauth/token'

# Scopes needed (read-only)
SCOPES = [
    'esi-characters.read_blueprints.v1',
    'esi-industry.read_character_jobs.v1',
    'esi-planets.manage_planets.v1',
    'esi-markets.read_character_orders.v1',
    'esi-contracts.read_character_contracts.v1',
    'esi-contracts.read_corporation_contracts.v1',
    'esi-skills.read_skills.v1',
]

# Load config from .env or set defaults
CLIENT_ID = os.getenv('ESI_CLIENT_ID', 'your_client_id_here')
CLIENT_SECRET = os.getenv('ESI_CLIENT_SECRET', 'your_client_secret_here')
REDIRECT_URI = os.getenv('ESI_REDIRECT_URI', 'http://localhost:8080/callback')

# File to store tokens
TOKENS_FILE = 'esi_tokens.json'

def load_tokens():
    """Load stored tokens from file."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_tokens(tokens):
    """Save tokens to file."""
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)

def get_oauth_session():
    """Create OAuth2 session."""
    return OAuth2Session(
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES
    )

def authorize_character(character_name=None):
    """Perform OAuth flow for a character."""
    oauth = get_oauth_session()

    # Generate state for security
    state = secrets.token_urlsafe(32)

    # Get authorization URL
    authorization_url, _ = oauth.authorization_url(
        AUTHORIZATION_BASE_URL,
        state=state
    )

    print(f"Open this URL in your browser to authorize: {authorization_url}")
    webbrowser.open(authorization_url)

    # Get the authorization response
    redirect_response = input("Paste the full redirect URL here: ")

    # Extract code from URL
    parsed_url = redirect_response
    if '?' in parsed_url:
        query = parsed_url.split('?', 1)[1]
        params = parse_qs(query)
        code = params.get('code', [None])[0]
        returned_state = params.get('state', [None])[0]
    else:
        print("Invalid redirect URL")
        return

    if returned_state != state:
        print("State mismatch! Possible CSRF attack.")
        return

    if not code:
        print("No authorization code received.")
        return

    # Exchange code for tokens
    token = oauth.fetch_token(
        TOKEN_URL,
        code=code,
        client_secret=CLIENT_SECRET
    )

    # Get character info
    headers = {'Authorization': f'Bearer {token["access_token"]}'}
    response = requests.get('https://esi.evetech.net/latest/characters/me/', headers=headers)
    if response.status_code == 200:
        char_info = response.json()
        char_id = str(char_info['CharacterID'])
        char_name = char_info['CharacterName']
    else:
        print("Failed to get character info")
        return

    # Store token
    tokens = load_tokens()
    tokens[char_id] = {
        'name': char_name,
        'access_token': token['access_token'],
        'refresh_token': token['refresh_token'],
        'expires_at': token['expires_at'],
        'token_type': token['token_type']
    }
    save_tokens(tokens)

    print(f"Successfully authorized character: {char_name} (ID: {char_id})")

def refresh_token(char_id):
    """Refresh an access token."""
    tokens = load_tokens()
    if char_id not in tokens:
        print(f"No token found for character ID {char_id}")
        return

    refresh_token = tokens[char_id]['refresh_token']

    # Create session with refresh token
    oauth = OAuth2Session(client_id=CLIENT_ID)

    # Refresh token
    new_token = oauth.refresh_token(
        TOKEN_URL,
        refresh_token=refresh_token,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )

    # Update stored token
    tokens[char_id].update({
        'access_token': new_token['access_token'],
        'refresh_token': new_token.get('refresh_token', refresh_token),
        'expires_at': new_token['expires_at'],
        'token_type': new_token['token_type']
    })
    save_tokens(tokens)

    print(f"Refreshed token for character: {tokens[char_id]['name']}")

def list_characters():
    """List all authorized characters."""
    tokens = load_tokens()
    if not tokens:
        print("No characters authorized yet.")
        return

    print("Authorized Characters:")
    for char_id, data in tokens.items():
        print(f"- {data['name']} (ID: {char_id})")

if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python esi_oauth.py <command>")
        print("Commands: authorize, refresh <char_id>, list")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'authorize':
        authorize_character()
    elif command == 'refresh' and len(sys.argv) > 2:
        refresh_token(sys.argv[2])
    elif command == 'list':
        list_characters()
    else:
        print("Invalid command")