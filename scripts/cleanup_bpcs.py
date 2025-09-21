#!/usr/bin/env python3
"""
EVE Obse    return (username, password)anup Script
Removes all Blueprint Copies (BPCs) from WordPress database.
BPCs are identified by having quantity != -1 (BPOs have quantity = -1).
"""

import os
import json
import requests
from dotenv import load_dotenv
import logging
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

def delete_bpc_posts(posts):
    """Delete BPC posts (quantity != -1)."""
    auth = get_wordpress_auth()
    deleted_count = 0
    bpo_count = 0

    for post in posts:
        post_id = post['id']
        title = post['title']['rendered']

        # Get the quantity meta field
        meta_url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
        meta_response = requests.get(meta_url, auth=auth)

        if meta_response.status_code != 200:
            logger.error(f"Failed to get meta for post {post_id}: {meta_response.status_code}")
            continue

        meta_data = meta_response.json()
        quantity = meta_data.get('meta', {}).get('_eve_bp_quantity', -1)

        # Convert to int if it's a string
        try:
            quantity = int(quantity)
        except (ValueError, TypeError):
            quantity = -1

        if quantity != -1:
            # This is a BPC, delete it
            delete_url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
            delete_response = requests.delete(delete_url, auth=auth, params={'force': True})

            if delete_response.status_code == 200:
                logger.info(f"Deleted BPC post: {title} (ID: {post_id}, quantity: {quantity})")
                deleted_count += 1
            else:
                logger.error(f"Failed to delete BPC post {post_id}: {delete_response.status_code} - {delete_response.text}")
        else:
            # This is a BPO, keep it
            logger.debug(f"Keeping BPO post: {title} (ID: {post_id}, quantity: {quantity})")
            bpo_count += 1

    logger.info(f"Cleanup complete: Deleted {deleted_count} BPCs, kept {bpo_count} BPOs")
    return deleted_count, bpo_count

def main():
    """Main cleanup function."""
    logger.info("Starting BPC cleanup process...")

    try:
        # Get all blueprint posts
        posts = get_all_blueprint_posts()

        if not posts:
            logger.info("No blueprint posts found")
            return

        # Delete BPC posts
        deleted, kept = delete_bpc_posts(posts)

        logger.info(f"BPC cleanup completed successfully. Deleted: {deleted}, Kept: {kept}")

    except Exception as e:
        logger.error(f"Error during BPC cleanup: {str(e)}")
        raise

if __name__ == "__main__":
    main()