#!/usr/bin/env python3
"""
EVE Observer Corrupted Blueprint Cleanup Script
Removes blueprint posts with non-standard slugs that contain corrupted data.
Standard slugs should be: blueprint-{item_id}
Corrupted slugs contain all blueprint data encoded in the slug.
"""

import os
import json
import requests
from dotenv import load_dotenv
import logging
import re
from config import *

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_wordpress_auth():
    """Get WordPress authentication tuple for requests."""
    username = os.getenv('WP_USERNAME')
    password = os.getenv('WP_APP_PASSWORD')

    if not username or not password:
        raise ValueError("WP_USERNAME and WP_APP_PASSWORD environment variables must be set")

    return (username, password)

def get_all_blueprint_posts():
    """Get all blueprint posts from WordPress with pagination."""
    auth = get_wordpress_auth()

    logger.info("Fetching all blueprint posts from WordPress...")
    posts = []
    page = 1

    while True:
        response = requests.get(
            f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint",
            auth=auth,
            params={'per_page': 100, 'page': page}
        )

        if response.status_code != 200:
            logger.error(f"Failed to fetch page {page}: {response.status_code} - {response.text}")
            break

        page_posts = response.json()
        if not page_posts:
            break

        posts.extend(page_posts)
        logger.debug(f"Fetched {len(page_posts)} posts from page {page}")
        page += 1

    logger.info(f"Found {len(posts)} blueprint posts total")
    return posts

def is_corrupted_slug(slug):
    """Check if a slug is corrupted (non-standard format)."""
    # Standard format: blueprint-{item_id}
    # Corrupted format: blueprint-item_id-{item_id}-location_flag-... etc.

    if not slug.startswith('blueprint-'):
        return False  # Not a blueprint slug at all

    # Check if it matches the standard pattern: blueprint-{digits}
    standard_pattern = re.compile(r'^blueprint-\d+$')
    if standard_pattern.match(slug):
        return False  # This is a standard slug

    # If it doesn't match the standard pattern but starts with blueprint-,
    # it's likely corrupted
    return True

def delete_corrupted_blueprint_posts(posts):
    """Delete blueprint posts with corrupted slugs."""
    auth = get_wordpress_auth()
    deleted_count = 0

    for post in posts:
        post_id = post['id']
        slug = post['slug']
        title = post['title']['rendered']

        if is_corrupted_slug(slug):
            # This is a corrupted slug, delete it
            delete_url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
            delete_response = requests.delete(delete_url, auth=auth, params={'force': True})

            if delete_response.status_code == 200:
                logger.info(f"Deleted corrupted blueprint post: {title} (ID: {post_id}, slug: {slug})")
                deleted_count += 1
            else:
                logger.error(f"Failed to delete corrupted blueprint post {post_id}: {delete_response.status_code} - {delete_response.text}")
        else:
            # This is a standard slug, keep it
            logger.debug(f"Keeping standard blueprint post: {title} (ID: {post_id}, slug: {slug})")

    logger.info(f"Cleanup complete: Deleted {deleted_count} corrupted blueprint posts")
    return deleted_count

def main():
    """Main cleanup function."""
    logger.info("Starting corrupted blueprint cleanup process...")

    try:
        # Get all blueprint posts
        posts = get_all_blueprint_posts()

        if not posts:
            logger.info("No blueprint posts found")
            return

        # Delete corrupted posts
        deleted = delete_corrupted_blueprint_posts(posts)

        logger.info(f"Corrupted blueprint cleanup completed successfully. Deleted: {deleted}")

    except Exception as e:
        logger.error(f"Error during corrupted blueprint cleanup: {str(e)}")
        raise

if __name__ == "__main__":
    main()