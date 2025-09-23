#!/usr/bin/env python3
"""
Fix featured images for existing posts - convert external URLs to proper WordPress featured images.
"""

import json
import logging
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from config import LOG_FILE, LOG_LEVEL, WP_BASE_URL

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def get_wp_auth():
    """Get WordPress authentication."""
    wp_user = os.getenv("WP_USER")
    wp_app_password = os.getenv("WP_APP_PASSWORD")
    if not wp_user or not wp_app_password:
        raise ValueError("WP_USER and WP_APP_PASSWORD environment variables must be set")
    return (wp_user, wp_app_password)


def upload_image_to_wordpress(image_url, filename, alt_text=""):
    """Upload an image to WordPress media library and return the media ID."""
    try:
        # Download the image
        response = requests.get(image_url, timeout=30)
        if response.status_code != 200:
            logger.warning(f"Failed to download image from {image_url}")
            return None

        # Prepare the file for upload
        files = {"file": (filename, response.content, response.headers.get("content-type", "image/png"))}
        data = {"alt_text": alt_text, "caption": alt_text}

        # Upload to WordPress
        upload_url = f"{WP_BASE_URL}/wp-json/wp/v2/media"
        upload_response = requests.post(upload_url, files=files, data=data, auth=get_wp_auth())

        if upload_response.status_code in [200, 201]:
            media_data = upload_response.json()
            return media_data["id"]
        else:
            logger.warning(
                f"Failed to upload image to WordPress: {upload_response.status_code} - {upload_response.text}"
            )
            return None

    except Exception as e:
        logger.error(f"Error uploading image {image_url}: {e}")
        return None


def fix_featured_images_for_post_type(post_type, post_type_name):
    """Fix featured images for a specific post type."""
    logger.info(f"Fixing featured images for {post_type_name} posts...")

    # Get all posts of this type
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/{post_type}", auth=get_wp_auth(), params={"per_page": 100})
    if response.status_code != 200:
        logger.error(f"Failed to fetch {post_type_name} posts: {response.status_code}")
        return

    posts = response.json()
    logger.info(f"Found {len(posts)} {post_type_name} posts")

    for post in posts:
        post_id = post["id"]
        meta = post.get("meta", {})
        featured_media = post.get("featured_media", 0)

        # Check if post has external URL but no featured media
        external_url = meta.get("_thumbnail_external_url")
        if external_url and not featured_media:
            logger.info(f"Fixing featured image for {post_type_name} post {post_id}: {external_url}")

            # Generate filename from URL
            filename = f"{post_type}_{post_id}.png"

            # Upload image and get media ID
            media_id = upload_image_to_wordpress(external_url, filename, post.get("title", {}).get("rendered", ""))

            if media_id:
                # Update post with featured media
                update_data = {
                    "featured_media": media_id,
                    "meta": {
                        k: v for k, v in meta.items() if k != "_thumbnail_external_url"
                    },  # Remove the custom field
                }

                update_url = f"{WP_BASE_URL}/wp-json/wp/v2/{post_type}/{post_id}"
                update_response = requests.put(update_url, json=update_data, auth=get_wp_auth())

                if update_response.status_code in [200, 201]:
                    logger.info(f"Successfully set featured image for {post_type_name} post {post_id}")
                else:
                    logger.error(
                        f"Failed to update {post_type_name} post {post_id}: "
                        f"{update_response.status_code} - {update_response.text}"
                    )
            else:
                logger.warning(f"Failed to upload image for {post_type_name} post {post_id}")
        elif external_url and featured_media:
            # Has both - just remove the custom field
            logger.info(f"Removing unnecessary custom field from {post_type_name} post {post_id}")
            update_data = {"meta": {k: v for k, v in meta.items() if k != "_thumbnail_external_url"}}

            update_url = f"{WP_BASE_URL}/wp-json/wp/v2/{post_type}/{post_id}"
            update_response = requests.put(update_url, json=update_data, auth=get_wp_auth())

            if update_response.status_code in [200, 201]:
                logger.info(f"Removed custom field from {post_type_name} post {post_id}")
            else:
                logger.error(
                    f"Failed to update {post_type_name} post {post_id}: "
                    f"{update_response.status_code} - {update_response.text}"
                )


def main():
    """Fix featured images for all post types."""
    logger.info("Starting featured image fix...")

    # Fix different post types
    post_types = [
        ("eve_blueprint", "blueprint"),
        ("eve_planet", "planet"),
        ("eve_corporation", "corporation"),
        ("eve_character", "character"),
        ("eve_contract", "contract"),
    ]

    for post_type, name in post_types:
        try:
            fix_featured_images_for_post_type(post_type, name)
        except Exception as e:
            logger.error(f"Error fixing {name} posts: {e}")

    logger.info("Featured image fix completed!")


if __name__ == "__main__":
    main()
