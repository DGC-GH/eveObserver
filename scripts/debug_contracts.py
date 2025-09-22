#!/usr/bin/env python3
"""
Debug script for corporation contracts
"""

import os
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
import logging

load_dotenv()

# Import config
from config import *

# Create a requests session
session = requests.Session()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_tokens():
    """Load stored tokens."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return {}

def fetch_esi(endpoint, access_token, max_retries=ESI_MAX_RETRIES):
    """Fetch data from ESI API with auth."""
    import time

    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {'Authorization': f'Bearer {access_token}'}

    for attempt in range(max_retries):
        try:
            response = session.get(url, headers=headers, timeout=ESI_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                logger.error(f"Authentication failed for {endpoint}")
                return None
            elif response.status_code == 403:
                logger.error(f"Access forbidden for {endpoint}")
                return None
            else:
                logger.error(f"ESI error for {endpoint}: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error fetching {endpoint}: {e}")
            return None

def fetch_public_esi(endpoint, max_retries=ESI_MAX_RETRIES):
    """Fetch data from ESI API (public endpoints)."""
    import time

    url = f"{ESI_BASE_URL}{endpoint}"

    for attempt in range(max_retries):
        try:
            response = session.get(url, timeout=ESI_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"ESI error for {endpoint}: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching {endpoint}: {e}")
            return None

def main():
    tokens = load_tokens()
    corp_id = 98092220  # No Mercy Incorporated

    # Find Dr FiLiN's token
    dr_filin_token = None
    for char_id, token_data in tokens.items():
        if token_data['name'] == 'Dr FiLiN':
            dr_filin_token = token_data['access_token']
            break

    if not dr_filin_token:
        logger.error("Dr FiLiN's token not found")
        return

    logger.info("Fetching corporation contracts...")

    # Fetch corporation contracts
    contracts = fetch_esi(f"/corporations/{corp_id}/contracts/", dr_filin_token)
    if not contracts:
        logger.error("Failed to fetch contracts")
        return

    logger.info(f"Fetched {len(contracts)} contracts")

    # Filter outstanding contracts
    outstanding = [c for c in contracts if c.get('status') == 'outstanding']
    logger.info(f"Outstanding contracts: {len(outstanding)}")

    # Check each outstanding contract
    for contract in outstanding:
        contract_id = contract['contract_id']
        logger.info(f"Contract {contract_id}: type={contract.get('type')}, assignee_id={contract.get('assignee_id')}, issuer_corp_id={contract.get('issuer_corporation_id')}, acceptor_id={contract.get('acceptor_id')}")

        # Fetch contract items
        items = fetch_esi(f"/corporations/{corp_id}/contracts/{contract_id}/items/", dr_filin_token)
        if items:
            logger.info(f"  Items: {len(items)}")
            has_bpo = False
            for item in items:
                type_id = item.get('type_id')
                quantity = item.get('quantity', 1)
                logger.info(f"    Item: type_id={type_id}, quantity={quantity}")
                if quantity == -1:  # BPO
                    has_bpo = True
                    # Get item name
                    type_data = fetch_public_esi(f"/universe/types/{type_id}")
                    if type_data:
                        name = type_data.get('name', f"Type {type_id}")
                        logger.info(f"      BPO: {name}")
                else:
                    # Check if it's a blueprint type even if quantity != -1
                    type_data = fetch_public_esi(f"/universe/types/{type_id}")
                    if type_data and 'Blueprint' in type_data.get('name', ''):
                        logger.info(f"      Blueprint but quantity={quantity}: {type_data.get('name')}")
                    else:
                        logger.info(f"      Not BPO: quantity={quantity}")
        else:
            logger.info("  No items found")

        logger.info("")

if __name__ == "__main__":
    main()