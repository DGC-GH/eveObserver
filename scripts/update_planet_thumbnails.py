#!/usr/bin/env python3
"""
Script to manually update planet thumbnail URLs based on planet type IDs.
Uses the 'icon' variation for planet images at 512px size.
"""

import requests
import json
import os
from datetime import datetime, timezone

# Import existing configuration and functions
from config import WP_BASE_URL, WP_PER_PAGE
from fetch_data import get_wp_auth, fetch_public_esi, fetch_planet_image

def update_planet_thumbnails():
    """Update all planet posts with new thumbnail URLs based on planet type IDs."""

    print("Fetching all planet posts...")

    # Get all planet posts
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_planet",
                          auth=get_wp_auth(),
                          params={'per_page': WP_PER_PAGE})

    if response.status_code != 200:
        print(f"Failed to fetch planet posts: {response.status_code} - {response.text}")
        return

    planets = response.json()
    print(f"Found {len(planets)} planet posts")

    updated_count = 0

    for planet in planets:
        post_id = planet['id']
        meta = planet.get('meta', {})

        # Get planet ID
        planet_id = meta.get('_eve_planet_id')
        if not planet_id:
            print(f"Skipping post {post_id} - no planet_id found")
            continue

        # Get planet type_id from universe data if not already stored
        planet_type_id = meta.get('_eve_planet_type_id')
        if not planet_type_id:
            # Fetch from universe endpoint
            planet_info = fetch_public_esi(f"/universe/planets/{planet_id}")
            if planet_info:
                planet_type_id = planet_info.get('type_id')
            else:
                print(f"Skipping post {post_id} - could not fetch planet info")
                continue

        # Construct new thumbnail URL
        new_thumbnail_url = fetch_planet_image(planet_type_id, size=512)

        # Get current thumbnail URL
        current_thumbnail_url = meta.get('_thumbnail_external_url')

        # Only update if different
        if current_thumbnail_url != new_thumbnail_url:
            print(f"Updating post {post_id} (Planet ID: {planet_id}, Type ID: {planet_type_id})")
            print(f"  Old URL: {current_thumbnail_url}")
            print(f"  New URL: {new_thumbnail_url}")

            # Update the post
            update_data = {
                'meta': {
                    '_thumbnail_external_url': new_thumbnail_url,
                    '_eve_planet_type_id': planet_type_id,  # Store the type_id for future use
                    '_eve_last_updated': datetime.now(timezone.utc).isoformat()
                }
            }

            update_response = requests.post(f"{WP_BASE_URL}/wp-json/wp/v2/eve_planet/{post_id}",
                                          json=update_data,
                                          auth=get_wp_auth())

            if update_response.status_code in [200, 201]:
                print(f"  ✓ Successfully updated post {post_id}")
                updated_count += 1
            else:
                print(f"  ✗ Failed to update post {post_id}: {update_response.status_code} - {update_response.text}")
        else:
            print(f"Post {post_id} (Planet ID: {planet_id}) already has correct URL")

    print(f"\nCompleted! Updated {updated_count} planet posts with new thumbnail URLs.")

if __name__ == '__main__':
    update_planet_thumbnails()