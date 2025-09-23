#!/usr/bin/env python3
"""
Check if the competitor contract 222262092 is a BPO or BPC
"""

import asyncio
import sys
import os

# Add the scripts directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from api_client import fetch_public_contract_items_async, fetch_public_esi

async def check_blueprint_type():
    """Check if contract 222262092 contains a BPO or BPC"""
    contract_id = 222262092

    print(f"Checking blueprint type for contract {contract_id}...")
    print("=" * 50)

    # Get contract items
    items = await fetch_public_contract_items_async(contract_id)
    if not items:
        print(f"No items found for contract {contract_id}")
        return

    print(f"Contract {contract_id} has {len(items)} items:")

    for item in items:
        type_id = item.get("type_id")
        quantity = item.get("quantity", 1)
        is_blueprint_copy = item.get("is_blueprint_copy", False)

        print(f"  Type ID: {type_id}")
        print(f"  Quantity: {quantity}")
        print(f"  Is Blueprint Copy: {is_blueprint_copy}")

        # Get item name
        item_data = await fetch_public_esi(f"/universe/types/{type_id}")
        if item_data:
            item_name = item_data.get("name", f"Unknown Item {type_id}")
            print(f"  Item Name: {item_name}")

            # Check if it's a blueprint
            if "Blueprint" in item_name:
                if quantity < 0:
                    print("  CONCLUSION: This is a BPO (Blueprint Original) - quantity is negative")
                elif quantity > 0:
                    if is_blueprint_copy:
                        print("  CONCLUSION: This is a BPC (Blueprint Copy) - is_blueprint_copy flag is True")
                    else:
                        print("  CONCLUSION: This appears to be a BPO (Blueprint Original) - positive quantity but no copy flag")
                else:
                    print("  CONCLUSION: Unable to determine BPO/BPC status")
            else:
                print("  CONCLUSION: This is not a blueprint")
        else:
            print("  Could not fetch item data")

        print()

if __name__ == "__main__":
    asyncio.run(check_blueprint_type())