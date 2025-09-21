#!/usr/bin/env python3
"""
Script to manually update blueprint thumbnail URLs based on type ID.
Uses the 'bp' variation for blueprint icons at 512px size.
"""

import requests
import json
import os
from datetime import datetime, timezone

# Import existing configuration and functions
from config import WP_BASE_URL, WP_PER_PAGE
from fetch_data import get_wp_auth

def update_blueprint_thumbnails():
    """Update all blueprint posts with new thumbnail URLs based on type ID."""

    print("Fetching all blueprint posts...")

    # First, get the total count
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint",
                          auth=get_wp_auth(),
                          params={'per_page': 1})

    if response.status_code != 200:
        print(f"Failed to get total count: {response.status_code} - {response.text}")
        return

    total_posts = int(response.headers.get('X-WP-Total', 0))
    pages = (total_posts + WP_PER_PAGE - 1) // WP_PER_PAGE  # Ceiling division

    print(f"Found {total_posts} blueprint posts across {pages} pages")

    updated_count = 0
    skipped_count = 0

    for page in range(1, pages + 1):
        print(f"Processing page {page}/{pages}...")

        response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint",
                              auth=get_wp_auth(),
                              params={'per_page': WP_PER_PAGE, 'page': page})

        if response.status_code != 200:
            print(f"Failed to fetch page {page}: {response.status_code} - {response.text}")
            continue

        blueprints = response.json()

        for bp in blueprints:
            post_id = bp['id']
            meta = bp.get('meta', {})

            # Get type ID from meta
            type_id = meta.get('_eve_bp_type_id')
            if not type_id:
                print(f"Skipping post {post_id} - no type_id found")
                skipped_count += 1
                continue

            # Construct new thumbnail URL
            new_thumbnail_url = f"https://images.evetech.net/types/{type_id}/bp?size=512"

            # Get current thumbnail URL
            current_thumbnail_url = meta.get('_thumbnail_external_url')

            # Only update if different
            if current_thumbnail_url != new_thumbnail_url:
                print(f"Updating post {post_id} (Type ID: {type_id})")

                # Update the post
                update_data = {
                    'meta': {
                        '_thumbnail_external_url': new_thumbnail_url,
                        '_eve_last_updated': datetime.now(timezone.utc).isoformat()
                    }
                }

                update_response = requests.post(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}",
                                              json=update_data,
                                              auth=get_wp_auth())

                if update_response.status_code in [200, 201]:
                    print(f"  ✓ Successfully updated post {post_id}")
                    updated_count += 1
                else:
                    print(f"  ✗ Failed to update post {post_id}: {update_response.status_code} - {update_response.text}")
            else:
                print(f"Post {post_id} (Type ID: {type_id}) already has correct URL")
                skipped_count += 1

    print(f"\nCompleted! Updated {updated_count} blueprint posts, skipped {skipped_count} posts (already correct or no type_id).")

if __name__ == '__main__':
    update_blueprint_thumbnails()