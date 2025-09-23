#!/usr/bin/env python3
"""
EVE Observer Cache Manager
Handles loading and saving of various caches for performance optimization.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from config import CACHE_DIR, BLUEPRINT_CACHE_FILE, BLUEPRINT_TYPE_CACHE_FILE, LOCATION_CACHE_FILE, STRUCTURE_CACHE_FILE, FAILED_STRUCTURES_FILE, WP_POST_ID_CACHE_FILE

logger = logging.getLogger(__name__)

def ensure_cache_dir() -> None:
    """Ensure cache directory exists."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def load_cache(cache_file: str) -> Dict[str, Any]:
    """Load cache from file."""
    ensure_cache_dir()
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache {cache_file}: {e}")
            return {}
    return {}

def save_cache(cache_file: str, data: Dict[str, Any]) -> None:
    """Save cache to file."""
    ensure_cache_dir()
    try:
        with open(cache_file, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save cache {cache_file}: {e}")

def load_blueprint_cache() -> Dict[str, Any]:
    """Load blueprint name cache."""
    return load_cache(BLUEPRINT_CACHE_FILE)

def save_blueprint_cache(cache: Dict[str, Any]) -> None:
    """Save blueprint name cache."""
    save_cache(BLUEPRINT_CACHE_FILE, cache)

def load_blueprint_type_cache() -> Dict[str, Any]:
    """Load blueprint type cache."""
    return load_cache(BLUEPRINT_TYPE_CACHE_FILE)

def save_blueprint_type_cache(cache: Dict[str, Any]) -> None:
    """Save blueprint type cache."""
    save_cache(BLUEPRINT_TYPE_CACHE_FILE, cache)

def load_location_cache() -> Dict[str, Any]:
    """Load location name cache."""
    return load_cache(LOCATION_CACHE_FILE)

def save_location_cache(cache: Dict[str, Any]) -> None:
    """Save location name cache."""
    save_cache(LOCATION_CACHE_FILE, cache)

def load_structure_cache() -> Dict[str, Any]:
    """Load structure name cache."""
    return load_cache(STRUCTURE_CACHE_FILE)

def save_structure_cache(cache: Dict[str, Any]) -> None:
    """Save structure name cache."""
    save_cache(STRUCTURE_CACHE_FILE, cache)

def load_failed_structures() -> Dict[str, Any]:
    """Load failed structures cache."""
    return load_cache(FAILED_STRUCTURES_FILE)

def save_failed_structures(cache: Dict[str, Any]) -> None:
    """Save failed structures cache."""
    save_cache(FAILED_STRUCTURES_FILE, cache)

def load_wp_post_id_cache() -> Dict[str, Any]:
    """Load WordPress post ID cache."""
    return load_cache(WP_POST_ID_CACHE_FILE)

def save_wp_post_id_cache(cache: Dict[str, Any]) -> None:
    """Save WordPress post ID cache."""
    save_cache(WP_POST_ID_CACHE_FILE, cache)

def get_cached_wp_post_id(cache: Dict[str, Any], post_type: str, item_id: int) -> Optional[int]:
    """Get cached WordPress post ID for an item."""
    key = f"{post_type}_{item_id}"
    return cache.get(key)

def set_cached_wp_post_id(cache: Dict[str, Any], post_type: str, item_id: int, post_id: int) -> None:
    """Cache WordPress post ID for an item."""
    key = f"{post_type}_{item_id}"
    cache[key] = post_id
    save_wp_post_id_cache(cache)