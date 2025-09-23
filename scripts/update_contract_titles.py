#!/usr/bin/env python3
"""
Script to update all contract titles to be more descriptive based on contract items.
"""

import json
from datetime import datetime, timezone

import requests

# Import existing configuration and functions
from config import WP_BASE_URL, WP_PER_PAGE
from fetch_data import generate_contract_title, get_wp_auth, load_blueprint_cache


def update_contract_titles():
    """Update all contract posts with descriptive titles based on items."""

    print("Fetching all contract posts...")

    # Get all contract posts
    response = requests.get(
        f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract", auth=get_wp_auth(), params={"per_page": WP_PER_PAGE}
    )

    if response.status_code != 200:
        print(f"Failed to fetch contract posts: {response.status_code} - {response.text}")
        return

    contracts = response.json()
    print(f"Found {len(contracts)} contract posts")

    blueprint_cache = load_blueprint_cache()
    updated_count = 0

    for contract in contracts:
        post_id = contract["id"]
        meta = contract.get("meta", {})

        # Get contract data from meta
        contract_id = meta.get("_eve_contract_id")
        if not contract_id:
            print(f"Skipping post {post_id} - no contract_id found")
            continue

        # Reconstruct contract data from meta
        contract_data = {
            "contract_id": contract_id,
            "type": meta.get("_eve_contract_type"),
            "status": meta.get("_eve_contract_status"),
            "issuer_id": meta.get("_eve_contract_issuer_id"),
            "issuer_corporation_id": meta.get("_eve_contract_issuer_corp_id"),
            "assignee_id": meta.get("_eve_contract_assignee_id"),
            "acceptor_id": meta.get("_eve_contract_acceptor_id"),
            "date_issued": meta.get("_eve_contract_date_issued"),
            "date_expired": meta.get("_eve_contract_date_expired"),
            "date_accepted": meta.get("_eve_contract_date_accepted"),
            "date_completed": meta.get("_eve_contract_date_completed"),
            "price": meta.get("_eve_contract_price"),
            "reward": meta.get("_eve_contract_reward"),
            "collateral": meta.get("_eve_contract_collateral"),
            "buyout": meta.get("_eve_contract_buyout"),
            "volume": meta.get("_eve_contract_volume"),
            "days_to_complete": meta.get("_eve_contract_days_to_complete"),
            "title": meta.get("_eve_contract_title"),
        }

        # Get contract items from meta
        contract_items = None
        items_json = meta.get("_eve_contract_items")
        if items_json:
            try:
                contract_items = json.loads(items_json)
            except:
                print(f"Warning: Could not parse items for contract {contract_id}")

        # Generate new title
        new_title = generate_contract_title(contract_data, contract_items, blueprint_cache)

        # Get current title
        current_title = contract.get("title", {}).get("rendered", "")

        # Only update if different
        if current_title != new_title:
            print(f"Updating contract {contract_id}")
            print(f"  Old title: {current_title}")
            print(f"  New title: {new_title}")

            # Update the post
            update_data = {"title": new_title, "meta": {"_eve_last_updated": datetime.now(timezone.utc).isoformat()}}

            update_response = requests.post(
                f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract/{post_id}", json=update_data, auth=get_wp_auth()
            )

            if update_response.status_code in [200, 201]:
                print(f"  ✓ Successfully updated contract {contract_id}")
                updated_count += 1
            else:
                print(
                    f"  ✗ Failed to update contract {contract_id}: {update_response.status_code} - {update_response.text}"
                )
        else:
            print(f"Contract {contract_id} already has correct title")

    print(f"\nCompleted! Updated {updated_count} contract posts with descriptive titles.")


if __name__ == "__main__":
    update_contract_titles()
