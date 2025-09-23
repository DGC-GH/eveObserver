#!/usr/bin/env python3
"""
Manual Citadel Name Updater
Allows manual updating of structure_names.json cache with citadel names.
"""

import json
import os
import sys
from datetime import datetime, timezone

# Configuration
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
STRUCTURE_CACHE_FILE = os.path.join(CACHE_DIR, "structure_names.json")


def load_structure_cache():
    """Load structure name cache."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    if os.path.exists(STRUCTURE_CACHE_FILE):
        try:
            with open(STRUCTURE_CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_structure_cache(cache):
    """Save structure name cache."""
    with open(STRUCTURE_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def add_citadel_name(citadel_id, name):
    """Add or update a citadel name in the cache."""
    cache = load_structure_cache()
    cache[str(citadel_id)] = name
    save_structure_cache(cache)
    print(f"Added/Updated citadel {citadel_id}: {name}")


def remove_citadel_name(citadel_id):
    """Remove a citadel from the cache."""
    cache = load_structure_cache()
    if str(citadel_id) in cache:
        del cache[str(citadel_id)]
        save_structure_cache(cache)
        print(f"Removed citadel {citadel_id} from cache")
    else:
        print(f"Citadel {citadel_id} not found in cache")


def list_citadel_names():
    """List all citadel names in the cache."""
    cache = load_structure_cache()
    if not cache:
        print("No citadel names in cache")
        return

    print("Current citadel names:")
    for citadel_id, name in cache.items():
        print(f"  {citadel_id}: {name}")


def batch_add_citadel_names(citadel_data):
    """Add multiple citadel names at once."""
    cache = load_structure_cache()
    updated = 0

    for citadel_id, name in citadel_data.items():
        cache[str(citadel_id)] = name
        updated += 1

    save_structure_cache(cache)
    print(f"Added/Updated {updated} citadel names")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python update_citadel_names.py list")
        print("  python update_citadel_names.py add <citadel_id> <name>")
        print("  python update_citadel_names.py remove <citadel_id>")
        print("  python update_citadel_names.py batch <json_file>")
        print("")
        print("Examples:")
        print("  python update_citadel_names.py add 1048892560419 'My Citadel Name'")
        print("  python update_citadel_names.py batch citadel_names.json")
        return

    command = sys.argv[1].lower()

    if command == "list":
        list_citadel_names()

    elif command == "add":
        if len(sys.argv) < 4:
            print("Usage: python update_citadel_names.py add <citadel_id> <name>")
            return
        try:
            citadel_id = int(sys.argv[2])
            name = " ".join(sys.argv[3:])
            add_citadel_name(citadel_id, name)
        except ValueError:
            print("Error: citadel_id must be a number")

    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: python update_citadel_names.py remove <citadel_id>")
            return
        try:
            citadel_id = int(sys.argv[2])
            remove_citadel_name(citadel_id)
        except ValueError:
            print("Error: citadel_id must be a number")

    elif command == "batch":
        if len(sys.argv) < 3:
            print("Usage: python update_citadel_names.py batch <json_file>")
            print('JSON file should contain: {"citadel_id": "name", ...}')
            return

        json_file = sys.argv[2]
        if not os.path.exists(json_file):
            print(f"Error: File {json_file} not found")
            return

        try:
            with open(json_file, "r") as f:
                citadel_data = json.load(f)
            batch_add_citadel_names(citadel_data)
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON in {json_file}")

    else:
        print(f"Unknown command: {command}")
        print("Use 'python update_citadel_names.py' for help")


if __name__ == "__main__":
    main()
