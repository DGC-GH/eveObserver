#!/usr/bin/env python3
"""Debug script to check specific contracts and their competition."""

import requests
import json
import sys
import os

# Add the scripts directory to the path so we can import from fetch_data.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fetch_data import get_wp_auth, WP_BASE_URL

def check_contract_details(contract_ids):
    """Check details of specific contracts."""
    for contract_id in contract_ids:
        print(f"\n=== Checking Contract {contract_id} ===")

        # Get contract from WordPress
        response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract", auth=get_wp_auth(),
                               params={'meta_key': '_eve_contract_id', 'meta_value': str(contract_id)})
        if response.status_code != 200:
            print(f"Failed to fetch contract {contract_id}: {response.status_code}")
            continue

        contracts = response.json()
        if not contracts:
            print(f"Contract {contract_id} not found in WordPress")
            continue

        contract = contracts[0]
        meta = contract.get('meta', {})

        # Extract contract details
        contract_price = meta.get('_eve_contract_price')
        contract_region = meta.get('_eve_contract_region_id')
        contract_items_json = meta.get('_eve_contract_items')
        contract_status = meta.get('_eve_contract_status')
        contract_type = meta.get('_eve_contract_type')

        print(f"Status: {contract_status}")
        print(f"Type: {contract_type}")
        print(f"Price: {contract_price}")
        print(f"Region: {contract_region}")

        if contract_items_json:
            try:
                items = json.loads(contract_items_json)
                if len(items) == 1:
                    item = items[0]
                    type_id = item.get('type_id')
                    quantity = item.get('quantity', 1)
                    price_per_item = float(contract_price) / quantity if quantity > 0 else 0
                    print(f"Item Type ID: {type_id}")
                    print(f"Quantity: {quantity}")
                    print(f"Price per item: {price_per_item}")
                else:
                    print(f"Multiple items: {len(items)}")
            except Exception as e:
                print(f"Error parsing items: {e}")
        else:
            print("No items data")

        # Now check for competing contracts
        if contract_items_json and contract_region and len(json.loads(contract_items_json)) == 1:
            item = json.loads(contract_items_json)[0]
            type_id = item.get('type_id')
            quantity = item.get('quantity', 1)
            price_per_item = float(contract_price) / quantity if quantity > 0 else 0

            print(f"\n--- Checking competition for type_id {type_id} in region {contract_region} ---")

            # Query for competing contracts
            params = {
                'meta_query[0][key]': '_eve_contract_region_id',
                'meta_query[0][value]': str(contract_region),
                'meta_query[0][compare]': '=',
                'meta_query[1][key]': '_eve_contract_item_types',
                'meta_query[1][value]': str(type_id),
                'meta_query[1][compare]': 'LIKE',
                'meta_query[relation]': 'AND',
                'per_page': 100
            }

            comp_response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_contract", auth=get_wp_auth(), params=params)
            if comp_response.status_code == 200:
                competing_contracts = comp_response.json()

                # Filter out this contract and finished/deleted contracts
                valid_competitors = [
                    c for c in competing_contracts
                    if c.get('meta', {}).get('_eve_contract_id') != str(contract_id) and
                    c.get('meta', {}).get('_eve_contract_status') == 'outstanding'
                ]

                print(f"Found {len(valid_competitors)} competing contracts")

                cheaper_found = False
                for comp in valid_competitors:
                    comp_meta = comp.get('meta', {})
                    comp_price = comp_meta.get('_eve_contract_price')
                    comp_items_json = comp_meta.get('_eve_contract_items')
                    comp_id = comp_meta.get('_eve_contract_id')

                    if comp_price and comp_items_json:
                        try:
                            comp_items = json.loads(comp_items_json)
                            if len(comp_items) == 1:
                                comp_item = comp_items[0]
                                comp_quantity = comp_item.get('quantity', 1)
                                if comp_quantity > 0:
                                    comp_price_per_item = float(comp_price) / comp_quantity
                                    if comp_price_per_item < price_per_item:
                                        print(f"CHEAPER COMPETITOR: Contract {comp_id} - {comp_price_per_item:.2f} ISK/item (vs {price_per_item:.2f})")
                                        cheaper_found = True
                                    else:
                                        print(f"Contract {comp_id} - {comp_price_per_item:.2f} ISK/item (more expensive)")
                        except Exception as e:
                            print(f"Error parsing competitor {comp_id}: {e}")

                if not cheaper_found:
                    print("NO CHEAPER COMPETITORS FOUND - Contract should NOT be marked as outbid!")
            else:
                print(f"Failed to fetch competitors: {comp_response.status_code}")

if __name__ == "__main__":
    contract_ids = [222697575, 222697571, 222697552]
    check_contract_details(contract_ids)