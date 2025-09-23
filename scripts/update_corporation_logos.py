#!/usr/bin/env python3
"""
Script to manually update corporation logo URLs.
Uses 512px size for corporation logos.
"""

import json
from datetime import datetime, timezone

import requests

# Import existing configuration and functions
from config import WP_BASE_URL, WP_PER_PAGE
from fetch_data import fetch_corporation_logo, get_wp_auth


def update_corporation_logos():
    """Update all corporation posts with new logo URLs at 512px size."""

    print("Fetching all corporation posts...")

    # Get all corporation posts
    response = requests.get(
        f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation", auth=get_wp_auth(), params={"per_page": WP_PER_PAGE}
    )

    if response.status_code != 200:
        print(f"Failed to fetch corporation posts: {response.status_code} - {response.text}")
        return

    corporations = response.json()
    print(f"Found {len(corporations)} corporation posts")

    updated_count = 0

    for corp in corporations:
        post_id = corp["id"]
        meta = corp.get("meta", {})

        # Get corp ID
        corp_id = meta.get("_eve_corp_id")
        if not corp_id:
            print(f"Skipping post {post_id} - no corp_id found")
            continue

        # Construct new logo URL
        new_logo_url = fetch_corporation_logo(corp_id)

        # Get current logo URL
        current_logo_url = meta.get("_thumbnail_external_url")

        # Only update if different
        if current_logo_url != new_logo_url:
            print(f"Updating post {post_id} (Corp ID: {corp_id})")
            print(f"  Old URL: {current_logo_url}")
            print(f"  New URL: {new_logo_url}")

            # Update the post
            update_data = {
                "meta": {
                    "_thumbnail_external_url": new_logo_url,
                    "_eve_last_updated": datetime.now(timezone.utc).isoformat(),
                }
            }

            update_response = requests.post(
                f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation/{post_id}", json=update_data, auth=get_wp_auth()
            )

            if update_response.status_code in [200, 201]:
                print(f"  ✓ Successfully updated post {post_id}")
                updated_count += 1
            else:
                print(f"  ✗ Failed to update post {post_id}: {update_response.status_code} - {update_response.text}")
        else:
            print(f"Post {post_id} (Corp ID: {corp_id}) already has correct URL")

    print(f"\nCompleted! Updated {updated_count} corporation posts with new logo URLs.")


if __name__ == "__main__":
    update_corporation_logos()
