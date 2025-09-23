#!/usr/bin/env python3
"""
EVE Observer Cache Manager
Handles loading and saving of various caches for performance optimization.
"""

import os
import json
import gzip
import logging
import asyncio
from typing import Any, Dict, List, Optional
import redis
r = redis.Redis()
from prometheus_client import Counter
cache_hits = Counter('cache_hits_total', 'Total cache hits')
cache_misses = Counter('cache_misses_total', 'Total cache misses')
from datetime import datetime, timezone
from config import CACHE_DIR, BLUEPRINT_CACHE_FILE, BLUEPRINT_TYPE_CACHE_FILE, LOCATION_CACHE_FILE, STRUCTURE_CACHE_FILE, FAILED_STRUCTURES_FILE, WP_POST_ID_CACHE_FILE

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_CONFIG = {
    'use_compression': True,
    'ttl_days': 30,  # Default TTL for cache entries
    'max_cache_size': 10000,  # Maximum number of entries per cache
    'batch_save_delay': 5,  # Seconds to delay batch saves
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
            if CACHE_CONFIG['use_compression']:
                with gzip.open(cache_file, 'rt', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
            
            # Clean up expired entries
            cleaned_data = _cleanup_expired_entries(data)
            if len(cleaned_data) != len(data):
                logger.info(f"Cleaned {len(data) - len(cleaned_data)} expired entries from {cache_file}")
                _cache_stats['expired_cleanups'] += len(data) - len(cleaned_data)
                # Save cleaned cache
                _save_cache_immediate(cache_file, cleaned_data)
            
            _cache_stats['loads'] += 1
            return cleaned_data
        except Exception as e:
            logger.warning(f"Failed to load cache {cache_file}: {e}")
            return {}
    return {}

def save_cache(cache_file: str, data: Dict[str, Any]) -> None:
    """Save cache to file with optional batching."""
    if CACHE_CONFIG.get('batch_save_delay', 0) > 0:
        _schedule_batch_save(cache_file, data)
    else:
        _save_cache_immediate(cache_file, data)

def _save_cache_immediate(cache_file: str, data: Dict[str, Any]) -> None:
    """Save cache immediately with compression."""
    ensure_cache_dir()
    try:
        # Add timestamps to new entries
        data_with_timestamps = _add_timestamps_to_cache(data)
        
        if CACHE_CONFIG['use_compression']:
            with gzip.open(cache_file, 'wt', encoding='utf-8') as f:
                json.dump(data_with_timestamps, f)
            _cache_stats['compressed_saves'] += 1
        else:
            with open(cache_file, 'w') as f:
                json.dump(data_with_timestamps, f)
        
        _cache_stats['saves'] += 1
    except Exception as e:
        logger.error(f"Failed to save cache {cache_file}: {e}")

def _add_timestamps_to_cache(data: Dict[str, Any]) -> Dict[str, Any]:
    """Add timestamps to cache entries for TTL support."""
    now = datetime.now(timezone.utc).isoformat()
    result = {}
    
    for key, value in data.items():
        if isinstance(value, dict) and '_timestamp' not in value:
            # Add timestamp to new entries
            value_copy = value.copy()
            value_copy['_timestamp'] = now
            result[key] = value_copy
        else:
            result[key] = value
    
    return result

def _cleanup_expired_entries(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove expired entries based on TTL."""
    if not CACHE_CONFIG['ttl_days']:
        return data
    
    now = datetime.now(timezone.utc)
    ttl_seconds = CACHE_CONFIG['ttl_days'] * 24 * 60 * 60
    cleaned = {}
    
    for key, value in data.items():
        if isinstance(value, dict) and '_timestamp' in value:
            try:
                entry_time = datetime.fromisoformat(value['_timestamp'].replace('Z', '+00:00'))
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
    _save_timers[cache_file] = loop.call_later(
        CACHE_CONFIG['batch_save_delay'], 
        _execute_batch_save, 
        cache_file
    )

def _execute_batch_save(cache_file: str) -> None:
    """Execute the batch save operation."""
    global _pending_saves, _save_timers
    
    if cache_file in _pending_saves:
        data = _pending_saves.pop(cache_file)
        _save_cache_immediate(cache_file, data)
        _cache_stats['batch_saves'] += 1
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
    # Note: save_wp_post_id_cache is called automatically via batch save

# Cache statistics and monitoring
_cache_stats = {
    'hits': 0,
    'misses': 0,
    'loads': 0,
    'saves': 0,
    'compressed_saves': 0,
    'batch_saves': 0,
    'expired_cleanups': 0
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
    total_requests = stats['hits'] + stats['misses']
    hit_rate = (stats['hits'] / total_requests * 100) if total_requests > 0 else 0
    
    logger.info(f"Cache Performance - Hits: {stats['hits']}, Misses: {stats['misses']}, "
                f"Hit Rate: {hit_rate:.1f}%, Loads: {stats['loads']}, Saves: {stats['saves']}, "
                f"Compressed Saves: {stats['compressed_saves']}, Batch Saves: {stats['batch_saves']}, "
                f"Expired Cleanups: {stats['expired_cleanups']}")

def get_cached_value_with_stats(cache: Dict[str, Any], key: str) -> Any:
    """Get a value from cache with statistics tracking."""
    if key in cache:
        _cache_stats['hits'] += 1
        return cache[key]
    else:
        _cache_stats['misses'] += 1
        return None

def set_cache_value_with_stats(cache: Dict[str, Any], key: str, value: Any, cache_file: str) -> None:
    """Set a value in cache with statistics tracking."""
    cache[key] = value
    save_cache(cache_file, cache)