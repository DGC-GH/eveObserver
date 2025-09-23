#!/usr/bin/env python3
"""
Debug script for corporation contracts
"""

import json
import logging
import os

import requests
from dotenv import load_dotenv

from api_client import fetch_esi_sync as fetch_esi
from api_client import fetch_public_esi_sync as fetch_public_esi
from config import TOKENS_FILE

load_dotenv()

# Create a requests session
session = requests.Session()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_tokens():
    """Load stored tokens."""
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return {}


def main():
    tokens = load_tokens()
    corp_id = 98092220  # No Mercy Incorporated

    # Find Dr FiLiN's token
    dr_filin_token = None
    for char_id, token_data in tokens.items():
        if token_data["name"] == "Dr FiLiN":
            dr_filin_token = token_data["access_token"]
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
    outstanding = [c for c in contracts if c.get("status") == "outstanding"]
    logger.info(f"Outstanding contracts: {len(outstanding)}")

    # Check each outstanding contract
    for contract in outstanding:
        contract_id = contract["contract_id"]
        logger.info(
            f"Contract {contract_id}: type={contract.get('type')}, "
            f"assignee_id={contract.get('assignee_id')}, "
            f"issuer_corp_id={contract.get('issuer_corporation_id')}, "
            f"acceptor_id={contract.get('acceptor_id')}"
        )

        # Fetch contract items
        items = fetch_esi(f"/corporations/{corp_id}/contracts/{contract_id}/items/", dr_filin_token)
        if items:
            logger.info(f"  Items: {len(items)}")
            for item in items:
                type_id = item.get("type_id")
                quantity = item.get("quantity", 1)
                logger.info(f"    Item: type_id={type_id}, quantity={quantity}")
                if quantity == -1:  # BPO
                    # Get item name
                    type_data = fetch_public_esi(f"/universe/types/{type_id}")
                    if type_data:
                        name = type_data.get("name", f"Type {type_id}")
                        logger.info(f"      BPO: {name}")
                else:
                    # Check if it's a blueprint type even if quantity != -1
                    type_data = fetch_public_esi(f"/universe/types/{type_id}")
                    if type_data and "Blueprint" in type_data.get("name", ""):
                        logger.info(f"      Blueprint but quantity={quantity}: {type_data.get('name')}")
                    else:
                        logger.info(f"      Not BPO: quantity={quantity}")
        else:
            logger.info("  No items found")

        logger.info("")


if __name__ == "__main__":
    main()
