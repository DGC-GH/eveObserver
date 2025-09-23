#!/usr/bin/env python3
"""
Blueprint Title Updater
Updates blueprint post titles to use proper citadel names instead of "Citadel {id}".
"""

import json
import os
import re
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

# Configuration - same as fetch_data.py
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
WP_BASE_URL = os.getenv("WP_URL", "http://localhost:8080")

# Cache files
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
STRUCTURE_CACHE_FILE = os.path.join(CACHE_DIR, "structure_names.json")
BLUEPRINT_CACHE_FILE = os.path.join(CACHE_DIR, "blueprint_names.json")


def load_structure_cache():
    """Load structure name cache."""
    if os.path.exists(STRUCTURE_CACHE_FILE):
        try:
            with open(STRUCTURE_CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def load_blueprint_cache():
    """Load blueprint name cache."""
    if os.path.exists(BLUEPRINT_CACHE_FILE):
        try:
            with open(BLUEPRINT_CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def get_wp_auth():
    """Get WordPress authentication tuple."""
    return (WP_USERNAME, WP_APP_PASSWORD)


def extract_citadel_id_from_title(title):
    """Extract citadel ID from a title containing 'Citadel {id}'."""
    match = re.search(r"Citadel (\d+)", title)
    return int(match.group(1)) if match else None


def update_blueprint_title(post_id, new_title, location_name):
    """Update a blueprint post's title and location name."""
    post_data = {
        "title": new_title,
        "meta": {"_eve_bp_location_name": location_name, "_eve_last_updated": datetime.now(timezone.utc).isoformat()},
    }

    url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
    response = requests.put(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        print(f"Updated blueprint post {post_id}: {new_title}")
        return True
    else:
        print(f"Failed to update blueprint post {post_id}: {response.status_code} - {response.text}")
        return False


def reconstruct_blueprint_title(current_title, old_location_name, new_location_name):
    """Reconstruct the blueprint title with the new location name."""
    return current_title.replace(old_location_name, new_location_name)


def main():
    """Main function to update blueprint titles."""
    if not all([WP_USERNAME, WP_APP_PASSWORD, WP_BASE_URL]):
        print("Error: WordPress credentials not configured in .env file")
        return

    # Load caches
    structure_cache = load_structure_cache()
    blueprint_cache = load_blueprint_cache()

    if not structure_cache:
        print("No citadel names found in structure cache. Run update_citadel_names.py first.")
        return

    print(f"Loaded {len(structure_cache)} citadel names from cache")

    # Fetch all blueprint posts
    page = 1
    per_page = 100
    updated_count = 0

    while True:
        response = requests.get(
            f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint",
            auth=get_wp_auth(),
            params={"per_page": per_page, "page": page},
        )

        if response.status_code != 200:
            print(f"Failed to fetch blueprint posts: {response.status_code} - {response.text}")
            break

        posts = response.json()
        if not posts:
            break

        print(f"Processing page {page} with {len(posts)} posts...")

        for post in posts:
            post_id = post["id"]
            current_title = post["title"]["rendered"]
            meta = post.get("meta", {})

            # Check if this post has a citadel placeholder
            if "Citadel " in current_title:
                citadel_id = extract_citadel_id_from_title(current_title)
                if citadel_id and str(citadel_id) in structure_cache:
                    citadel_name = structure_cache[str(citadel_id)]
                    old_location_name = f"Citadel {citadel_id}"
                    new_location_name = citadel_name

                    # Reconstruct title
                    new_title = reconstruct_blueprint_title(current_title, old_location_name, new_location_name)

                    # Update the post
                    if update_blueprint_title(post_id, new_title, new_location_name):
                        updated_count += 1

        page += 1

        # Check if there are more pages
        total_pages = int(response.headers.get("X-WP-TotalPages", 1))
        if page > total_pages:
            break

    print(f"\nCompleted! Updated {updated_count} blueprint posts with proper citadel names.")


if __name__ == "__main__":
    main()
