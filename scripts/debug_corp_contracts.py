#!/usr/bin/env python3
"""Debug script to check corporation contracts for blueprints."""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fetch_data import (
    load_blueprint_cache,
    load_tokens,
    fetch_corporation_contracts,
    fetch_corporation_contract_items,
    refresh_token
)

def main():
    # Corporation ID to check
    corp_id = 98092220  # No Mercy Incorporated

    # Load blueprint cache
    blueprint_cache = load_blueprint_cache()
    print(f"Loaded blueprint cache with {len(blueprint_cache)} entries")

    # Load tokens
    tokens = load_tokens()
    if not tokens:
        print("No tokens found. Run 'python esi_oauth.py authorize' first.")
        return

    # Find a valid token for this corporation
    access_token = None
    char_name = None

    for char_id, token_data in tokens.items():
        # Refresh token if needed
        try:
            from datetime import datetime, timezone
            expired = datetime.now(timezone.utc) > datetime.fromisoformat(token_data.get('expires_at', '2000-01-01T00:00:00+00:00'))
        except:
            expired = True

        if expired:
            print(f"Token for {token_data['name']} expired, refreshing...")
            new_token = refresh_token(token_data['refresh_token'])
            if new_token:
                token_data.update(new_token)
                # Save updated tokens
                from fetch_data import save_tokens
                save_tokens(tokens)
                print(f"Refreshed token for {token_data['name']}")
            else:
                print(f"Failed to refresh token for {token_data['name']}")
                continue

        access_token = token_data['access_token']
        char_name = token_data['name']

        # Try to fetch corporation contracts to test access
        contracts = fetch_corporation_contracts(corp_id, access_token)
        if contracts is not None:
            print(f"Successfully accessed corporation contracts using {char_name}'s token")
            break
        else:
            print(f"Failed to access corporation contracts with {char_name}'s token")
            access_token = None

    if not access_token:
        print("No valid token found for corporation access")
        return

    # Fetch corporation contracts
    print(f"Fetching contracts for corporation {corp_id}...")
    contracts = fetch_corporation_contracts(corp_id, access_token)

    if not contracts:
        print("No contracts found or access denied")
        return

    print(f"Found {len(contracts)} contracts")

    # Check each contract for blueprints
    contracts_with_blueprints = 0
    total_contracts_checked = 0

    for contract in contracts:
        contract_id = contract.get('contract_id')
        status = contract.get('status', 'unknown')

        # Only check contracts issued by this corporation (like the main system does)
        issuer_corp_id = contract.get('issuer_corporation_id')
        if issuer_corp_id != corp_id:
            continue

        total_contracts_checked += 1

        # Fetch contract items
        contract_items = fetch_corporation_contract_items(corp_id, contract_id, access_token)

        if not contract_items:
            print(f"Contract {contract_id} ({status}): No items found")
            continue

        # Check for blueprints
        has_blueprint = False
        blueprint_items = []

        for item in contract_items:
            type_id = item.get('type_id')
            if type_id:
                type_id_str = str(type_id)
                if type_id_str in blueprint_cache:
                    has_blueprint = True
                    blueprint_items.append({
                        'type_id': type_id,
                        'name': blueprint_cache[type_id_str],
                        'quantity': item.get('quantity', 1)
                    })

        if has_blueprint:
            contracts_with_blueprints += 1
            print(f"Contract {contract_id} ({status}): CONTAINS BLUEPRINTS")
            for bp in blueprint_items:
                print(f"  - {bp['name']} (ID: {bp['type_id']}, Qty: {bp['quantity']})")
        else:
            print(f"Contract {contract_id} ({status}): No blueprints found")

    print(f"\nSummary:")
    print(f"Total contracts checked: {total_contracts_checked}")
    print(f"Contracts with blueprints: {contracts_with_blueprints}")
    print(f"Contracts without blueprints: {total_contracts_checked - contracts_with_blueprints}")

if __name__ == "__main__":
    main()