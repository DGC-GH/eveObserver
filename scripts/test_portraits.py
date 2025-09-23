#!/usr/bin/env python3
"""
Test script for character portrait functionality
Fetches character portraits and sets them as featured images for existing character posts.
"""

import json
import logging
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from config import ESI_BASE_URL, ESI_TIMEOUT, LOG_FILE, LOG_LEVEL, WP_APP_PASSWORD, WP_BASE_URL, WP_USERNAME

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def get_wp_auth():
    """Get WordPress authentication tuple."""
    return (WP_USERNAME, WP_APP_PASSWORD)


def fetch_character_portrait(char_id):
    """Fetch character portrait URLs from ESI."""
    endpoint = f"/characters/{char_id}/portrait/"
    url = f"{ESI_BASE_URL}{endpoint}"
    response = requests.get(url, timeout=ESI_TIMEOUT)
    if response.status_code == 200:
        return response.json()
    else:
        logger.warning(f"Failed to fetch portrait for character {char_id}: {response.status_code}")
        return None


def check_image_exists(filename):
    """Check if an image with the given filename already exists in WordPress media library."""
    # Search for media by filename
    search_url = f"{WP_BASE_URL}/wp-json/wp/v2/media"
    params = {"search": filename, "per_page": 100}
    response = requests.get(search_url, auth=get_wp_auth(), params=params)
    if response.status_code == 200:
        media_items = response.json()
        # Look for exact filename match
        for item in media_items:
            if item.get("title", {}).get("rendered") == filename or item.get("slug") == filename:
                return item["id"]
    return None


def remove_duplicate_images(base_filename):
    """Remove duplicate images with WordPress number suffixes."""
    duplicates = []
    search_url = f"{WP_BASE_URL}/wp-json/wp/v2/media"
    params = {"search": base_filename, "per_page": 100}
    response = requests.get(search_url, auth=get_wp_auth(), params=params)
    if response.status_code == 200:
        media_items = response.json()
        # Find items with suffixes like -1, -2, etc.
        base_items = []
        suffixed_items = []
        for item in media_items:
            title = item.get("title", {}).get("rendered", "")
            if title == base_filename:
                base_items.append(item)
            elif title.startswith(base_filename + "-"):
                suffixed_items.append(item)

        # If we have multiple base items or suffixed items, keep only one
        if len(base_items) > 1:
            # Keep the first one, delete the rest
            for item in base_items[1:]:
                duplicates.append(item)
        # Delete all suffixed items as they are duplicates
        duplicates.extend(suffixed_items)

        # Delete duplicates
        for item in duplicates:
            delete_url = f"{WP_BASE_URL}/wp-json/wp/v2/media/{item['id']}"
            delete_response = requests.delete(delete_url, auth=get_wp_auth())
            if delete_response.status_code in [200, 204]:
                logger.info(f"Deleted duplicate image: {item.get('title', {}).get('rendered')}")
            else:
                logger.warning(f"Failed to delete duplicate image {item['id']}: {delete_response.status_code}")


def upload_image_to_wordpress(image_url, filename, alt_text=""):
    """Upload an image to WordPress media library using external URL and return the media ID."""
    try:
        # First check if image already exists
        existing_id = check_image_exists(filename)
        if existing_id:
            logger.info(f"Image already exists: {filename} (ID: {existing_id})")
            return existing_id

        # Clean up any duplicates before uploading
        remove_duplicate_images(filename)

        # Use WordPress's built-in external URL support
        data = {"source_url": image_url, "alt_text": alt_text, "caption": alt_text}

        # Upload to WordPress using source_url
        upload_url = f"{WP_BASE_URL}/wp-json/wp/v2/media"
        upload_response = requests.post(upload_url, json=data, auth=get_wp_auth())

        if upload_response.status_code in [200, 201]:
            media_data = upload_response.json()
            logger.info(f"Successfully uploaded image: {filename} (ID: {media_data['id']})")
            return media_data["id"]
        else:
            logger.warning(f"Failed to create media from URL: {upload_response.status_code} - {upload_response.text}")
            return None

    except Exception as e:
        logger.error(f"Error creating media from URL {image_url}: {e}")
        return None


def update_character_portrait(post_id, char_id, char_name):
    """Update a character post with its portrait as featured image."""
    # Fetch portrait data
    portrait_data = fetch_character_portrait(char_id)
    if not portrait_data or "px64x64" not in portrait_data:
        logger.warning(f"No portrait data available for character: {char_name}")
        return False

    image_url = portrait_data["px64x64"]
    filename = f"character_{char_id}_portrait.png"

    # Upload or get existing image
    media_id = upload_image_to_wordpress(image_url, filename, char_name)
    if not media_id:
        logger.error(f"Failed to get/create media for character: {char_name}")
        return False

    # Update the post with external thumbnail URL
    post_data = {"meta": {"_thumbnail_external_url": image_url}}

    update_url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_character/{post_id}"
    response = requests.put(update_url, json=post_data, auth=get_wp_auth())

    logger.info(f"Update response for {char_name}: {response.status_code}")
    if response.status_code in [200, 201]:
        logger.info(f"Set portrait for character: {char_name}")
        return True
    else:
        logger.error(f"Failed to update character {char_name}: {response.status_code} - {response.text}")
        return False


def main():
    """Main test function."""
    logger.info("Starting character portrait test...")

    # Fetch all existing character posts
    page = 1
    per_page = 100
    all_posts = []

    while True:
        posts_url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_character"
        params = {"per_page": per_page, "page": page}
        response = requests.get(posts_url, auth=get_wp_auth(), params=params)

        if response.status_code != 200:
            logger.error(f"Failed to fetch character posts page {page}: {response.status_code}")
            break

        posts = response.json()
        if not posts:
            break

        all_posts.extend(posts)
        page += 1

        # Check if there are more pages
        total_pages = int(response.headers.get("X-WP-TotalPages", 1))
        if page > total_pages:
            break

    logger.info(f"Found {len(all_posts)} character posts")

    # Process each character post
    success_count = 0
    for post in all_posts:
        post_id = post["id"]
        meta = post.get("meta", {})
        char_id = meta.get("_eve_char_id")
        char_name = meta.get("_eve_char_name", post.get("title", {}).get("rendered", f"Character {post_id}"))

        if not char_id:
            logger.warning(f"No character ID found for post {post_id}")
            continue

        # Check if already has featured image
        current_featured = post.get("featured_media", 0)
        if current_featured:
            logger.info(f"Character {char_name} already has featured image, skipping")
            continue

        # Update with portrait
        if update_character_portrait(post_id, char_id, char_name):
            success_count += 1

    logger.info(f"Successfully set portraits for {success_count} out of {len(all_posts)} characters")


if __name__ == "__main__":
    main()
