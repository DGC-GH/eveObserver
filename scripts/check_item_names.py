#!/usr/bin/env python3
"""
Quick script to look up item names for specific type_ids
"""

import asyncio
import sys
import os

# Add the scripts directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from api_client import fetch_public_esi, cleanup_session

async def get_item_name(type_id: int) -> str:
    """Get item name from ESI for a given type_id"""
    item_data = await fetch_public_esi(f"/universe/types/{type_id}")
    if item_data:
        return item_data.get("name", f"Unknown Item {type_id}")
    return f"Unknown Item {type_id}"

async def main():
    # Check the item name for type_id 29050 (from the debug script)
    type_id = 29050
    name = await get_item_name(type_id)
    print(f"Type ID {type_id}: {name}")

    # Check a few more type_ids that were in the debug output
    other_type_ids = [25267, 57147, 25508, 47740, 60482]
    for tid in other_type_ids:
        name = await get_item_name(tid)
        print(f"Type ID {tid}: {name}")

    await cleanup_session()

if __name__ == "__main__":
    asyncio.run(main())