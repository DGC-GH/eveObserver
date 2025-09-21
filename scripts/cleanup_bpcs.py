#!/usr/bin/env python3
"""
EVE Observer BPC Cleanup Script
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
    """Get WordPress authentication headers."""
    username = os.getenv('WP_USERNAME')
    password = os.getenv('WP_APP_PASSWORD')

    if not username or not password:
        raise ValueError("WP_USERNAME and WP_APP_PASSWORD environment variables must be set")

    auth = requests.auth.HTTPBasicAuth(username, password)
    return {'Authorization': f'Basic {auth.username}:{auth.password}'}

def get_all_blueprint_posts():
    """Get all blueprint posts from WordPress."""
    headers = get_wordpress_auth()
    url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint"

    logger.info("Fetching all blueprint posts from WordPress...")
    response = requests.get(url, headers=headers, params={'per_page': 100})

    if response.status_code != 200:
        logger.error(f"Failed to fetch blueprint posts: {response.status_code} - {response.text}")
        return []

    posts = response.json()
    logger.info(f"Found {len(posts)} blueprint posts")

    return posts

def delete_bpc_posts(posts):
    """Delete BPC posts (quantity != -1)."""
    headers = get_wordpress_auth()
    deleted_count = 0
    bpo_count = 0

    for post in posts:
        post_id = post['id']
        title = post['title']['rendered']

        # Get the quantity meta field
        meta_url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post_id}"
        meta_response = requests.get(meta_url, headers=headers)

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
            delete_response = requests.delete(delete_url, headers=headers, params={'force': True})

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