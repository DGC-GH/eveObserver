#!/usr/bin/env python3
"""
EVE Observer Cache Manager
Handles loading and saving of various caches for performance optimization.
"""

import asyncio
import gzip
import json
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Optional

from config import (
    BLUEPRINT_CACHE_FILE,
    BLUEPRINT_TYPE_CACHE_FILE,
    CACHE_DIR,
    FAILED_STRUCTURES_FILE,
    LOCATION_CACHE_FILE,
    STRUCTURE_CACHE_FILE,
    WP_POST_ID_CACHE_FILE,
)

# Prometheus-style metrics for monitoring
try:
    from prometheus_client import Counter, Gauge, Histogram

    CACHE_HITS = Counter("eve_cache_hits_total", "Total cache hits", ["cache_type"])
    CACHE_MISSES = Counter("eve_cache_misses_total", "Total cache misses", ["cache_type"])
    CACHE_SIZE = Gauge("eve_cache_size", "Current cache size", ["cache_type"])
    API_REQUEST_DURATION = Histogram("eve_api_request_duration_seconds", "API request duration", ["endpoint_type"])
    CACHE_OPERATION_DURATION = Histogram(
        "eve_cache_operation_duration_seconds", "Cache operation duration", ["operation"]
    )

    METRICS_ENABLED = True
except ImportError:
    # Fallback if prometheus_client is not available
    METRICS_ENABLED = False
    CACHE_HITS = CACHE_MISSES = CACHE_SIZE = API_REQUEST_DURATION = CACHE_OPERATION_DURATION = None

logger = logging.getLogger(__name__)


class LRUCache:
    """In-memory LRU cache with disk persistence."""

    def __init__(self, max_size: int = 1000, cache_file: str = None, auto_save: bool = True):
        self.max_size = max_size
        self.cache_file = cache_file
        self.auto_save = auto_save
        self.cache = OrderedDict()
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load cache from disk if file exists."""
        if self.cache_file and os.path.exists(self.cache_file):
            try:
                data = load_cache(self.cache_file)
                # Sort by access time if available, otherwise load all
                for key, value in data.items():
                    if isinstance(value, dict) and "_last_access" in value:
                        # Keep only recent entries based on max_size
                        if len(self.cache) < self.max_size:
                            self.cache[key] = value
                    else:
                        # Legacy data without timestamps
                        if len(self.cache) < self.max_size:
                            self.cache[key] = value
                logger.debug(f"Loaded {len(self.cache)} entries from {self.cache_file}")
            except Exception as e:
                logger.warning(f"Failed to load LRU cache from {self.cache_file}: {e}")

    def _save_to_disk(self) -> None:
        """Save cache to disk."""
        if self.cache_file and self.auto_save:
            try:
                # Convert OrderedDict to regular dict for JSON serialization
                data_to_save = dict(self.cache)
                save_cache(self.cache_file, data_to_save)
                logger.debug(f"Saved {len(self.cache)} entries to {self.cache_file}")
            except Exception as e:
                logger.error(f"Failed to save LRU cache to {self.cache_file}: {e}")

    def get(self, key: str) -> Any:
        """Get value from cache, moving it to most recently used."""
        if key in self.cache:
            # Move to end (most recently used)
            value = self.cache.pop(key)
            self.cache[key] = value
            # Update last access time
            if isinstance(value, dict):
                value["_last_access"] = datetime.now(timezone.utc).isoformat()
            _cache_stats["hits"] += 1
            return value.get("_value", value) if isinstance(value, dict) and "_value" in value else value
        _cache_stats["misses"] += 1
        return None

    def put(self, key: str, value: Any) -> None:
        """Put value in cache, evicting least recently used if necessary."""
        # Remove if already exists
        if key in self.cache:
            self.cache.pop(key)
        elif len(self.cache) >= self.max_size:
            # Evict least recently used
            evicted_key, _ = self.cache.popitem(last=False)
            logger.debug(f"Evicted {evicted_key} from LRU cache")

        # Store with metadata
        cache_entry = {
            "_value": value,
            "_last_access": datetime.now(timezone.utc).isoformat(),
            "_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.cache[key] = cache_entry

        # Auto-save periodically
        if len(self.cache) % 100 == 0:  # Save every 100 operations
            self._save_to_disk()

    def __contains__(self, key: str) -> bool:
        return key in self.cache

    def __len__(self) -> int:
        return len(self.cache)

    def clear(self) -> None:
        """Clear the cache."""
        self.cache.clear()
        self._save_to_disk()

    def flush(self) -> None:
        """Flush cache to disk."""
        self._save_to_disk()


# Global LRU cache instances
_blueprint_lru_cache = None
_location_lru_cache = None
_structure_lru_cache = None


def get_blueprint_lru_cache() -> LRUCache:
    """Get or create blueprint LRU cache instance."""
    global _blueprint_lru_cache
    if _blueprint_lru_cache is None:
        _blueprint_lru_cache = LRUCache(max_size=2000, cache_file=BLUEPRINT_CACHE_FILE)
    return _blueprint_lru_cache


def get_location_lru_cache() -> LRUCache:
    """Get or create location LRU cache instance."""
    global _location_lru_cache
    if _location_lru_cache is None:
        _location_lru_cache = LRUCache(max_size=1500, cache_file=LOCATION_CACHE_FILE)
    return _location_lru_cache


def get_structure_lru_cache() -> LRUCache:
    """Get or create structure LRU cache instance."""
    global _structure_lru_cache
    if _structure_lru_cache is None:
        _structure_lru_cache = LRUCache(max_size=1000, cache_file=STRUCTURE_CACHE_FILE)
    return _structure_lru_cache


# Cache configuration
CACHE_CONFIG = {
    "use_compression": True,
    "ttl_days": 30,  # Default TTL for cache entries
    "max_cache_size": 10000,  # Maximum number of entries per cache
    "batch_save_delay": 5,  # Seconds to delay batch saves
}

# Global cache instances for batch operations
_cache_instances = {}
_pending_saves = {}
_save_timers = {}


def ensure_cache_dir() -> None:
    """Ensure cache directory exists."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


def load_cache(cache_file: str) -> Dict[str, Any]:
    """Load cache from file with compression support and TTL cleanup."""
    ensure_cache_dir()
    if os.path.exists(cache_file):
        try:
            start_time = time.time()
            logger.info(f"Loading cache from {cache_file}...")
            
            # Try loading as uncompressed JSON first (for backward compatibility)
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
            except Exception:
                # If uncompressed fails, try compressed
                with gzip.open(cache_file, "rt", encoding="utf-8") as f:
                    data = json.load(f)

            # Clean up expired entries
            cleaned_data = _cleanup_expired_entries(data)
            if len(cleaned_data) != len(data):
                logger.info(f"Cleaned {len(data) - len(cleaned_data)} expired entries from {cache_file}")
                _cache_stats["expired_cleanups"] += len(data) - len(cleaned_data)
                # Save cleaned cache
                _save_cache_immediate(cache_file, cleaned_data)

            load_time = time.time() - start_time
            logger.info(f"✓ Cache loaded from {cache_file}: {len(cleaned_data)} entries in {load_time:.2f}s")
            _cache_stats["loads"] += 1
            return cleaned_data
        except Exception as e:
            logger.warning(f"Failed to load cache {cache_file}: {e}")
            return {}
    return {}


def save_cache(cache_file: str, data: Dict[str, Any]) -> None:
    """Save cache to file with optional batching."""
    if CACHE_CONFIG.get("batch_save_delay", 0) > 0:
        _schedule_batch_save(cache_file, data)
    else:
        _save_cache_immediate(cache_file, data)


def _save_cache_immediate(cache_file: str, data: Dict[str, Any]) -> None:
    """Save cache immediately with compression."""
    ensure_cache_dir()
    try:
        start_time = time.time()
        logger.debug(f"Saving cache to {cache_file} ({len(data)} entries)...")
        
        # Add timestamps to new entries
        data_with_timestamps = _add_timestamps_to_cache(data)

        if CACHE_CONFIG["use_compression"]:
            with gzip.open(cache_file, "wt", encoding="utf-8") as f:
                json.dump(data_with_timestamps, f)
            _cache_stats["compressed_saves"] += 1
        else:
            with open(cache_file, "w") as f:
                json.dump(data_with_timestamps, f)

        save_time = time.time() - start_time
        logger.debug(f"✓ Cache saved to {cache_file}: {len(data)} entries in {save_time:.3f}s")
        _cache_stats["saves"] += 1
    except Exception as e:
        logger.error(f"Failed to save cache {cache_file}: {e}")


def _add_timestamps_to_cache(data: Dict[str, Any]) -> Dict[str, Any]:
    """Add timestamps to cache entries for TTL support."""
    now = datetime.now(timezone.utc).isoformat()
    result = {}

    for key, value in data.items():
        if isinstance(value, dict) and "_timestamp" not in value:
            # Add timestamp to new entries
            value_copy = value.copy()
            value_copy["_timestamp"] = now
            result[key] = value_copy
        else:
            result[key] = value

    return result


def _cleanup_expired_entries(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove expired entries based on TTL."""
    if not CACHE_CONFIG["ttl_days"]:
        return data

    now = datetime.now(timezone.utc)
    ttl_seconds = CACHE_CONFIG["ttl_days"] * 24 * 60 * 60
    cleaned = {}

    for key, value in data.items():
        if isinstance(value, dict) and "_timestamp" in value:
            try:
                entry_time = datetime.fromisoformat(value["_timestamp"].replace("Z", "+00:00"))
                if (now - entry_time).total_seconds() < ttl_seconds:
                    cleaned[key] = value
            except (ValueError, TypeError):
                # Keep entries with invalid timestamps
                cleaned[key] = value
        else:
            # Keep entries without timestamps (legacy data)
            cleaned[key] = value

    return cleaned


def _schedule_batch_save(cache_file: str, data: Dict[str, Any]) -> None:
    """Schedule a batch save with delay to reduce I/O operations."""
    global _pending_saves, _save_timers

    _pending_saves[cache_file] = data

    # Cancel existing timer if any
    if cache_file in _save_timers:
        _save_timers[cache_file].cancel()

    # Schedule new save
    loop = asyncio.get_event_loop()
    _save_timers[cache_file] = loop.call_later(CACHE_CONFIG["batch_save_delay"], _execute_batch_save, cache_file)


def _execute_batch_save(cache_file: str) -> None:
    """Execute the batch save operation."""
    global _pending_saves, _save_timers

    if cache_file in _pending_saves:
        data = _pending_saves.pop(cache_file)
        _save_cache_immediate(cache_file, data)
        _cache_stats["batch_saves"] += 1
        logger.debug(f"Batch saved cache: {cache_file}")

    if cache_file in _save_timers:
        del _save_timers[cache_file]


def flush_pending_saves() -> None:
    """Flush all pending batch saves immediately."""
    global _pending_saves, _save_timers

    for cache_file, data in _pending_saves.items():
        _save_cache_immediate(cache_file, data)
        if cache_file in _save_timers:
            _save_timers[cache_file].cancel()

    _pending_saves.clear()
    _save_timers.clear()
    logger.info("Flushed all pending cache saves")


async def async_flush_pending_saves() -> None:
    """Flush all pending batch saves asynchronously."""
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, flush_pending_saves)


def preload_common_caches() -> None:
    """Preload frequently accessed caches on startup for better performance."""
    logger.info("Preloading common caches...")
    
    # Preload blueprint type cache (used for determining if items are blueprints)
    try:
        bp_type_cache = load_blueprint_type_cache()
        logger.info(f"Preloaded blueprint type cache: {len(bp_type_cache)} entries")
    except Exception as e:
        logger.warning(f"Failed to preload blueprint type cache: {e}")
    
    # Preload blueprint name cache
    try:
        bp_cache = load_blueprint_cache()
        logger.info(f"Preloaded blueprint cache: {len(bp_cache)} entries")
    except Exception as e:
        logger.warning(f"Failed to preload blueprint cache: {e}")
    
    # Preload location cache
    try:
        loc_cache = load_location_cache()
        logger.info(f"Preloaded location cache: {len(loc_cache)} entries")
    except Exception as e:
        logger.warning(f"Failed to preload location cache: {e}")


def load_blueprint_cache() -> Dict[str, Any]:
    """Load blueprint name cache."""
    return load_cache(BLUEPRINT_CACHE_FILE)


def save_blueprint_cache(cache: Dict[str, Any]) -> None:
    """Save blueprint name cache."""
    save_cache(BLUEPRINT_CACHE_FILE, cache)
    # Also update LRU cache
    lru_cache = get_blueprint_lru_cache()
    for key, value in cache.items():
        lru_cache.put(key, value)


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
    # Also update LRU cache
    lru_cache = get_location_lru_cache()
    for key, value in cache.items():
        lru_cache.put(key, value)


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
    # Note: save_wp_post_id_cache is called automatically via batch save


# Cache statistics and monitoring
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "loads": 0,
    "saves": 0,
    "compressed_saves": 0,
    "batch_saves": 0,
    "expired_cleanups": 0,
}


def get_cache_stats() -> Dict[str, int]:
    """Get cache performance statistics."""
    return _cache_stats.copy()


def reset_cache_stats() -> None:
    """Reset cache statistics."""
    global _cache_stats
    _cache_stats = {k: 0 for k in _cache_stats}


def log_cache_performance() -> None:
    """Log cache performance statistics."""
    stats = get_cache_stats()
    total_requests = stats["hits"] + stats["misses"]
    hit_rate = (stats["hits"] / total_requests * 100) if total_requests > 0 else 0

    logger.info(
        f"Cache Performance - Hits: {stats['hits']}, Misses: {stats['misses']}, "
        f"Hit Rate: {hit_rate:.1f}%, Loads: {stats['loads']}, Saves: {stats['saves']}, "
        f"Compressed Saves: {stats['compressed_saves']}, Batch Saves: {stats['batch_saves']}, "
        f"Expired Cleanups: {stats['expired_cleanups']}"
    )


def get_cached_value_with_stats(cache: Dict[str, Any], key: str, cache_type: str = "unknown") -> Any:
    """Get a value from cache with statistics and metrics tracking."""
    start_time = time.time()

    if key in cache:
        _cache_stats["hits"] += 1
        if METRICS_ENABLED:
            CACHE_HITS.labels(cache_type=cache_type).inc()
            CACHE_OPERATION_DURATION.labels(operation="get_hit").observe(time.time() - start_time)
        return cache[key]
    else:
        _cache_stats["misses"] += 1
        if METRICS_ENABLED:
            CACHE_MISSES.labels(cache_type=cache_type).inc()
            CACHE_OPERATION_DURATION.labels(operation="get_miss").observe(time.time() - start_time)
        return None


@lru_cache(maxsize=1000)
def get_cached_blueprint_name(type_id: str) -> Optional[str]:
    """Get cached blueprint name with LRU caching for performance."""
    cache = get_blueprint_lru_cache()
    return cache.get(type_id)


@lru_cache(maxsize=1000)
def get_cached_location_name(location_id: str) -> Optional[str]:
    """Get cached location name with LRU caching for performance."""
    cache = get_location_lru_cache()
    return cache.get(location_id)


def set_cache_value_with_stats(cache: Dict[str, Any], key: str, value: Any, cache_file: str) -> None:
    """Set a value in cache with statistics tracking."""
    cache[key] = value
    save_cache(cache_file, cache)
