#!/usr/bin/env python3
"""
Debug script to check contract items.
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from fetch_data import load_tokens, fetch_corporation_contract_items, refresh_token, load_blueprint_cache
from datetime import datetime, timezone

def main():
    tokens = load_tokens()
    if not tokens:
        print("No tokens found")
        return

    # Find Dr FiLiN's token
    dr_filin_token = None
    for char_id, token_data in tokens.items():
        if token_data['name'] == 'Dr FiLiN':
            # Check if expired
            try:
                expired = datetime.now(timezone.utc) > datetime.fromisoformat(token_data.get('expires_at', '2000-01-01T00:00:00+00:00'))
            except:
                expired = True
            if expired:
                print("Dr FiLiN's token expired, refreshing...")
                new_token = refresh_token(token_data['refresh_token'])
                if new_token:
                    token_data.update(new_token)
                    # Save updated tokens
                    import json
                    with open('esi_tokens.json', 'w') as f:
                        json.dump(tokens, f, indent=2)
                else:
                    print("Failed to refresh token")
                    return
            dr_filin_token = token_data['access_token']
            break

    if not dr_filin_token:
        print("Dr FiLiN's token not found")
        return

    blueprint_cache = load_blueprint_cache()
    print(f"Blueprint cache has {len(blueprint_cache)} entries")

    corp_id = 98092220  # No Mercy Incorporated

    # Check a few contracts that we know have blueprints
    contract_ids = [222641777, 222641803, 222641814]  # First few from our debug

    for contract_id in contract_ids:
        print(f"\nChecking contract {contract_id}:")
        items = fetch_corporation_contract_items(corp_id, contract_id, dr_filin_token)
        if not items:
            print("  No items found")
            continue

        print(f"  Found {len(items)} items:")
        has_blueprint = False
        for item in items:
            type_id = item.get('type_id')
            quantity = item.get('quantity', 1)
            is_in_cache = str(type_id) in blueprint_cache if type_id else False
            print(f"    Type ID: {type_id}, Quantity: {quantity}, In cache: {is_in_cache}")
            if is_in_cache:
                has_blueprint = True
                print(f"      Blueprint name: {blueprint_cache[str(type_id)]}")

        print(f"  Contract has blueprint: {has_blueprint}")

if __name__ == "__main__":
    main()