#!/usr/bin/env python3
"""
Cache manager for contract expansion data.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, List, Any, Optional

# Add the scripts directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

import aiohttp
from api_client import fetch_public_esi, get_session
from config import ESI_BASE_URL

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ContractCacheManager:
    """Manages caching for contract expansion data."""

    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def get_issuer_cache_path(self) -> str:
        return os.path.join(self.cache_dir, "issuer_names_cache.json")

    def get_type_cache_path(self) -> str:
        return os.path.join(self.cache_dir, "type_data_cache.json")

    def get_contract_items_cache_path(self) -> str:
        return os.path.join(self.cache_dir, "contract_items_cache.json")

    async def load_issuer_cache(self) -> Dict[str, str]:
        """Load cached issuer names."""
        cache_path = self.get_issuer_cache_path()
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load issuer cache: {e}")
        return {}

    async def save_issuer_cache(self, issuer_cache: Dict[str, str]) -> None:
        """Save issuer names cache."""
        cache_path = self.get_issuer_cache_path()
        try:
            with open(cache_path, 'w') as f:
                json.dump(issuer_cache, f, indent=2)
            logger.info(f"Saved {len(issuer_cache)} issuer names to cache")
        except Exception as e:
            logger.error(f"Failed to save issuer cache: {e}")

    async def load_type_cache(self) -> Dict[str, Dict[str, Any]]:
        """Load cached type data."""
        cache_path = self.get_type_cache_path()
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load type cache: {e}")
        return {}

    async def save_type_cache(self, type_cache: Dict[str, Dict[str, Any]]) -> None:
        """Save type data cache."""
        cache_path = self.get_type_cache_path()
        try:
            with open(cache_path, 'w') as f:
                json.dump(type_cache, f, indent=2)
            logger.info(f"Saved {len(type_cache)} type entries to cache")
        except Exception as e:
            logger.error(f"Failed to save type cache: {e}")

    async def load_contract_items_cache(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load cached contract items."""
        cache_path = self.get_contract_items_cache_path()
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load contract items cache: {e}")
        return {}

    async def save_contract_items_cache(self, items_cache: Dict[str, List[Dict[str, Any]]]) -> None:
        """Save contract items cache."""
        cache_path = self.get_contract_items_cache_path()
        try:
            with open(cache_path, 'w') as f:
                json.dump(items_cache, f, indent=2)
            logger.info(f"Saved {len(items_cache)} contract items to cache")
        except Exception as e:
            logger.error(f"Failed to save contract items cache: {e}")

    async def get_missing_issuer_names(self, issuer_ids: List[int], existing_cache: Dict[str, str]) -> Dict[str, str]:
        """Get issuer names that are not in cache."""
        missing_ids = [str(issuer_id) for issuer_id in issuer_ids if str(issuer_id) not in existing_cache]

        if not missing_ids:
            return {}

        logger.info(f"Fetching {len(missing_ids)} missing issuer names...")

        # Batch fetch missing issuer names
        batch_size = 1000
        new_names = {}

        for i in range(0, len(missing_ids), batch_size):
            batch_ids = missing_ids[i:i + batch_size]
            try:
                # Use the universe/names endpoint for batch resolution
                sess = await get_session()
                async with sess.post(
                    f"{ESI_BASE_URL}/universe/names/",
                    json=[int(id) for id in batch_ids],
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                        response.raise_for_status()
                        names_data = await response.json()

                        for name_info in names_data:
                            entity_id = str(name_info.get("id"))
                            name = name_info.get("name")
                            if entity_id and name:
                                new_names[entity_id] = name

            except Exception as e:
                logger.warning(f"Failed to fetch batch of issuer names: {e}")

        return new_names

    async def get_missing_type_data(self, type_ids: List[int], existing_cache: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Get type data that is not in cache."""
        missing_ids = [str(type_id) for type_id in type_ids if str(type_id) not in existing_cache]

        if not missing_ids:
            return {}

        logger.info(f"Fetching {len(missing_ids)} missing type data entries...")

        new_types = {}
        for type_id in missing_ids:
            try:
                type_data = await fetch_public_esi(f"/universe/types/{type_id}/")
                if type_data:
                    new_types[type_id] = type_data
            except Exception as e:
                logger.warning(f"Failed to fetch type data for {type_id}: {e}")

        return new_types


# Global cache manager instance
cache_manager = ContractCacheManager()


async def preload_caches_for_contracts(contracts: List[Dict[str, Any]]) -> None:
    """Preload caches with data needed for contract expansion."""
    logger.info("Preloading caches for contract expansion...")

    # Collect all issuer IDs
    issuer_ids = set()
    type_ids = set()

    for contract in contracts:
        if contract.get("issuer_id"):
            issuer_ids.add(contract["issuer_id"])
        if contract.get("issuer_corporation_id"):
            issuer_ids.add(contract["issuer_corporation_id"])

    # Load existing caches
    issuer_cache = await cache_manager.load_issuer_cache()
    type_cache = await cache_manager.load_type_cache()

    # Get missing issuer names
    missing_issuers = await cache_manager.get_missing_issuer_names(list(issuer_ids), issuer_cache)
    if missing_issuers:
        issuer_cache.update(missing_issuers)
        await cache_manager.save_issuer_cache(issuer_cache)

    logger.info(f"Issuer cache: {len(issuer_cache)} total entries")
    logger.info(f"Type cache: {len(type_cache)} total entries")


if __name__ == "__main__":
    # Test the cache manager
    asyncio.run(preload_caches_for_contracts([]))