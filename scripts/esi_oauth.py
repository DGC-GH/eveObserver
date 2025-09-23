#!/usr/bin/env python3
"""
EVE ESI OAuth Script for EVE Observer
Handles OAuth flow to obtain access and refresh tokens for EVE characters.
"""

import json
import logging
import os
import secrets
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth2Session

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ESI OAuth endpoints
AUTHORIZATION_BASE_URL = "https://login.eveonline.com/v2/oauth/authorize"
TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"

# Scopes needed (read-only)
SCOPES = [
    "esi-characters.read_blueprints.v1",
    "esi-industry.read_character_jobs.v1",
    "esi-planets.manage_planets.v1",
    "esi-markets.read_character_orders.v1",
    "esi-contracts.read_character_contracts.v1",
    "esi-skills.read_skills.v1",
    "esi-universe.read_structures.v1",
    # Corporation scopes
    "esi-contracts.read_corporation_contracts.v1",
    "esi-assets.read_corporation_assets.v1",
    "esi-wallet.read_corporation_wallets.v1",
    "esi-markets.read_corporation_orders.v1",
    "esi-industry.read_corporation_jobs.v1",
    "esi-corporations.read_blueprints.v1",
    "esi-corporations.read_structures.v1",
    # Additional character scopes
    "esi-assets.read_assets.v1",
    "esi-wallet.read_character_wallet.v1",
    "esi-killmails.read_killmails.v1",
    "esi-location.read_location.v1",
    "esi-location.read_online.v1",
    "esi-characters.read_loyalty.v1",
    "esi-clones.read_clones.v1",
    "esi-clones.read_implants.v1",
    "esi-characters.read_standings.v1",
]

# Load config from .env or set defaults
CLIENT_ID = os.getenv("ESI_CLIENT_ID", "your_client_id_here")
CLIENT_SECRET = os.getenv("ESI_CLIENT_SECRET", "your_client_secret_here")
REDIRECT_URI = os.getenv("ESI_REDIRECT_URI", "http://localhost:8080/callback")

if CLIENT_ID == "your_client_id_here" or CLIENT_SECRET == "your_client_secret_here":
    logger.error("ESI_CLIENT_ID and ESI_CLIENT_SECRET must be set in .env file")
    logger.error("Get them from https://developers.eveonline.com/")
    sys.exit(1)

# File to store tokens
TOKENS_FILE = "esi_tokens.json"


def load_tokens():
    """Load stored tokens from file."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_tokens(tokens):
    """Save tokens to file."""
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def get_oauth_session():
    """Create OAuth2 session."""
    return OAuth2Session(client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, scope=SCOPES)


def authorize_character(character_name=None):
    """Perform OAuth flow for a character."""
    oauth = get_oauth_session()

    # Generate state for security
    state = secrets.token_urlsafe(32)

    # Get authorization URL
    authorization_url, _ = oauth.authorization_url(AUTHORIZATION_BASE_URL, state=state)

    print(f"Open this URL in your browser to authorize: {authorization_url}")
    webbrowser.open(authorization_url)

    # Get the authorization response
    redirect_response = input("Paste the full redirect URL here: ")

    # Extract code from URL
    parsed_url = redirect_response
    if "?" in parsed_url:
        query = parsed_url.split("?", 1)[1]
        params = parse_qs(query)
        code = params.get("code", [None])[0]
        returned_state = params.get("state", [None])[0]
    else:
        logger.error("Invalid redirect URL")
        return

    if returned_state != state:
        logger.error("State mismatch! Possible CSRF attack.")
        return

    if not code:
        logger.error("No authorization code received.")
        return

    # Exchange code for tokens
    try:
        token = oauth.fetch_token(TOKEN_URL, code=code, client_secret=CLIENT_SECRET)
        logger.info("Token obtained successfully")
    except Exception as e:
        logger.error(f"Failed to obtain token: {e}")
        return

    # Get character info
    headers = {"Authorization": f'Bearer {token["access_token"]}'}
    response = requests.get("https://login.eveonline.com/oauth/verify", headers=headers)
    logger.debug(f"Character info response: {response.status_code}")
    if response.status_code == 200:
        char_info = response.json()
        char_id = str(char_info["CharacterID"])
        char_name = char_info["CharacterName"]
    else:
        logger.error(f"Failed to get character info: {response.status_code} - {response.text}")
        return

    # Store token
    tokens = load_tokens()
    tokens[char_id] = {
        "name": char_name,
        "access_token": token["access_token"],
        "refresh_token": token["refresh_token"],
        "expires_at": token["expires_at"],
        "token_type": token["token_type"],
    }
    save_tokens(tokens)

    logger.info(f"Successfully authorized character: {char_name} (ID: {char_id})")


def refresh_token(char_id):
    """Refresh an access token."""
    tokens = load_tokens()
    if char_id not in tokens:
        logger.error(f"No token found for character ID {char_id}")
        return

    refresh_token_str = tokens[char_id]["refresh_token"]

    # Use Basic auth as per ESI docs
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token_str}
    response = requests.post(TOKEN_URL, data=data, auth=(CLIENT_ID, CLIENT_SECRET))
    if response.status_code == 200:
        token_data = response.json()
        # Update stored token
        tokens[char_id].update(
            {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", refresh_token_str),
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"]),
                "token_type": token_data["token_type"],
            }
        )
        save_tokens(tokens)

        logger.info(f"Refreshed token for character: {tokens[char_id]['name']}")
    else:
        logger.error(f"Failed to refresh token: {response.status_code} - {response.text}")


def authorize_all_characters():
    """Authorize all characters in sequence."""
    print("Starting authorization for all characters.")
    print("You'll need to authorize each character one by one in your browser.")
    print("For each character, copy the redirect URL and paste it when prompted.\n")

    while True:
        try:
            authorize_character()
            print("\nCharacter authorized successfully!")
            choice = input("Authorize another character? (y/n): ").strip().lower()
            if choice != "y":
                break
        except KeyboardInterrupt:
            print("\nAuthorization cancelled.")
            break
        except Exception as e:
            print(f"Error during authorization: {e}")
            choice = input("Try again? (y/n): ").strip().lower()
            if choice != "y":
                break

    print("Authorization process complete.")
    list_characters()


def list_characters():
    """List all authorized characters."""
    tokens = load_tokens()
    if not tokens:
        print("No characters authorized yet.")
        return

    print("Authorized Characters:")
    for char_id, data in tokens.items():
        print(f"- {data['name']} (ID: {char_id})")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python esi_oauth.py <command>")
        print("Commands: authorize, authorize_all, refresh <char_id>, list")
        sys.exit(1)

    command = sys.argv[1]

    if command == "authorize":
        authorize_character()
    elif command == "authorize_all":
        authorize_all_characters()
    elif command == "refresh" and len(sys.argv) > 2:
        refresh_token(sys.argv[2])
    elif command == "list":
        list_characters()
    else:
        print("Invalid command")
