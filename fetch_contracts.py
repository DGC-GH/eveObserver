#!/usr/bin/env python3
"""
Simple script to fetch and update all_contracts_forge.json
"""

import asyncio
import json
import os
import sys

# Add the scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from contract_processor import fetch_and_expand_all_forge_contracts

async def main():
    print("Fetching all Forge contracts...")
    contracts = await fetch_and_expand_all_forge_contracts()
    print(f"Fetched {len(contracts)} contracts")

if __name__ == "__main__":
    asyncio.run(main())