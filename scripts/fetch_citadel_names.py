#!/usr/bin/env python3
"""
Fetch missing citadel names and update structure cache.
"""

import json
import logging
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from config import (
    CACHE_DIR,
    ESI_BASE_URL,
    ESI_MAX_RETRIES,
    ESI_TIMEOUT,
    LOG_FILE,
    LOG_LEVEL,
    STRUCTURE_CACHE_FILE,
    TOKENS_FILE,
)

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def load_tokens():
    """Load stored tokens."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return {}


def load_structure_cache():
    """Load structure name cache."""
    return load_cache(STRUCTURE_CACHE_FILE)


def save_structure_cache(cache):
    """Save structure name cache."""
    save_cache(STRUCTURE_CACHE_FILE, cache)


def load_cache(cache_file):
    """Load cache from file."""
    ensure_cache_dir()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_cache(cache_file, data):
    """Save cache to file."""
    ensure_cache_dir()
    with open(cache_file, "w") as f:
        json.dump(data, f)


def ensure_cache_dir():
    """Ensure cache directory exists."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


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
                error_limit_reset = response.headers.get("X-ESI-Error-Limit-Reset")

                if error_limit_reset:
                    wait_time = int(error_limit_reset) + 1  # Add 1 second buffer
                    logger.info(f"RATE LIMIT: Waiting {wait_time} seconds for public endpoint...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Fallback: wait 60 seconds if no reset header
                    logger.info("RATE LIMIT: Waiting 60 seconds for public endpoint (no reset header)...")
                    time.sleep(60)
                    continue
            elif response.status_code == 420:  # Error limited
                error_limit_reset = response.headers.get("X-ESI-Error-Limit-Reset")

                if error_limit_reset:
                    wait_time = int(error_limit_reset) + 1
                    logger.info(f"ERROR LIMIT: Waiting {wait_time} seconds for public endpoint...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.info("ERROR LIMIT: Waiting 60 seconds for public endpoint...")
                    time.sleep(60)
                    continue
            elif response.status_code >= 500:
                # Server error, retry
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # Exponential backoff
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
                wait_time = 2**attempt
                logger.warning(f"TIMEOUT: Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                logger.error("TIMEOUT: Max retries exceeded")
                return None
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt
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
    headers = {"Authorization": f"Bearer {access_token}"}

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
                error_limit_reset = response.headers.get("X-ESI-Error-Limit-Reset")

                if error_limit_reset:
                    wait_time = int(error_limit_reset) + 1
                    logger.info(f"RATE LIMIT: Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.info("RATE LIMIT: Waiting 60 seconds (no reset header)...")
                    time.sleep(60)
                    continue
            elif response.status_code == 420:  # Error limited
                error_limit_reset = response.headers.get("X-ESI-Error-Limit-Reset")

                if error_limit_reset:
                    wait_time = int(error_limit_reset) + 1
                    logger.info(f"ERROR LIMIT: Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.info("ERROR LIMIT: Waiting 60 seconds...")
                    time.sleep(60)
                    continue
            elif response.status_code >= 500:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
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
                wait_time = 2**attempt
                logger.warning(f"TIMEOUT: Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                logger.error("TIMEOUT: Max retries exceeded")
                return None
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                logger.warning(f"NETWORK ERROR: {e}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"NETWORK ERROR: {e}. Max retries exceeded")
                return None

    return None


def refresh_token(refresh_token):
    """Refresh an access token."""
    from datetime import datetime, timedelta

    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    client_id = os.getenv("ESI_CLIENT_ID")
    client_secret = os.getenv("ESI_CLIENT_SECRET")
    response = requests.post(
        "https://login.eveonline.com/v2/oauth/token", data=data, auth=(client_id, client_secret), timeout=30
    )
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


def main():
    """Fetch missing citadel names and update cache."""
    # Citadel IDs to fetch
    citadel_ids = ["1048892560419", "1048497019672"]

    # Load existing structure cache
    structure_cache = load_structure_cache()
    logger.info(f"Loaded {len(structure_cache)} existing structure names")

    # Load tokens
    tokens = load_tokens()
    if not tokens:
        logger.error("No authorized characters found. Run 'python esi_oauth.py authorize' first.")
        return

    # Use Sir FiLiN specifically as requested
    preferred_char_id = "90162477"  # Sir FiLiN
    if preferred_char_id in tokens:
        char_id = preferred_char_id
        logger.info(f"Using Sir FiLiN as requested ({char_id})")
    else:
        logger.error(f"Sir FiLiN ({preferred_char_id}) not found in tokens")
        return

    token_data = tokens[char_id]

    # Refresh token if needed
    try:
        expired = datetime.now(timezone.utc) > datetime.fromisoformat(
            token_data.get("expires_at", "2000-01-01T00:00:00+00:00")
        )
    except (ValueError, TypeError):
        expired = True

    if expired:
        logger.info("Refreshing token...")
        new_token = refresh_token(token_data["refresh_token"])
        if new_token:
            token_data.update(new_token)
            # Save updated tokens
            with open(TOKENS_FILE, "w") as f:
                json.dump(tokens, f)
        else:
            logger.error("Failed to refresh token")
            return

    access_token = token_data["access_token"]

    # Fetch each citadel name
    for citadel_id in citadel_ids:
        if citadel_id in structure_cache:
            logger.info(f"Citadel {citadel_id} already in cache: {structure_cache[citadel_id]}")
            continue

        logger.info(f"Fetching name for citadel {citadel_id}...")

        citadel_name = None

        # Try public access first (some structures might be public)
        struct_data = fetch_public_esi(f"/universe/structures/{citadel_id}")
        if struct_data:
            citadel_name = struct_data.get("name", f"Citadel {citadel_id}")
            logger.info(f"Got name via public access: {citadel_name}")

        # If public access failed, try Sir FiLiN
        if not citadel_name:
            logger.info("Public access failed, trying Sir FiLiN...")

            # Refresh token if needed
            try:
                expired = datetime.now(timezone.utc) > datetime.fromisoformat(
                    token_data.get("expires_at", "2000-01-01T00:00:00+00:00")
                )
            except (ValueError, TypeError):
                expired = True

            if expired:
                logger.info("Refreshing Sir FiLiN's token...")
                new_token = refresh_token(token_data["refresh_token"])
                if new_token:
                    token_data.update(new_token)
                    # Save updated tokens
                    with open(TOKENS_FILE, "w") as f:
                        json.dump(tokens, f)
                else:
                    logger.error("Failed to refresh Sir FiLiN's token")
                    continue

            access_token = token_data["access_token"]
            struct_data = fetch_esi(f"/universe/structures/{citadel_id}", char_id, access_token)

            if struct_data:
                citadel_name = struct_data.get("name", f"Citadel {citadel_id}")
                logger.info(f"Got name via Sir FiLiN: {citadel_name}")
            else:
                logger.error(f"Sir FiLiN also denied access to citadel {citadel_id}")

        if citadel_name:
            structure_cache[citadel_id] = citadel_name
            logger.info("Added citadel {}: {}".format(citadel_id, citadel_name))
        else:
            logger.error(f"Failed to fetch name for citadel {citadel_id} with Sir FiLiN")

    # Save updated cache
    save_structure_cache(structure_cache)
    logger.info(f"Saved {len(structure_cache)} structure names to cache")


if __name__ == "__main__":
    main()
