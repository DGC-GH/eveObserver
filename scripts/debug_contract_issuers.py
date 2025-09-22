#!/usr/bin/env python3
"""
Debug script to check corporation contract issuers.
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from fetch_data import load_tokens, fetch_corporation_contracts, refresh_token
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

    corp_id = 98092220  # No Mercy Incorporated
    contracts = fetch_corporation_contracts(corp_id, dr_filin_token)

    if not contracts:
        print("No contracts found")
        return

    print(f"Found {len(contracts)} contracts")

    issuer_counts = {}
    status_counts = {}

    for contract in contracts:
        issuer_corp_id = contract.get('issuer_corporation_id')
        status = contract.get('status', 'unknown')
        contract_id = contract.get('contract_id')

        if issuer_corp_id not in issuer_counts:
            issuer_counts[issuer_corp_id] = 0
        issuer_counts[issuer_corp_id] += 1

        if status not in status_counts:
            status_counts[status] = 0
        status_counts[status] += 1

        # Check if this contract would be processed
        if status in ['finished', 'deleted']:
            continue
        elif issuer_corp_id != corp_id:
            continue

        print(f"Contract {contract_id}: issuer_corp={issuer_corp_id}, status={status}")

    print("\nIssuer corporation counts:")
    for issuer_id, count in issuer_counts.items():
        print(f"  {issuer_id}: {count} contracts")

    print("\nStatus counts:")
    for status, count in status_counts.items():
        print(f"  {status}: {count} contracts")

if __name__ == "__main__":
    main()