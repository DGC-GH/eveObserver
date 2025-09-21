#!/usr/bin/env python3
"""
Verify that character posts have featured images set
"""

import requests
import json
from config import *
from dotenv import load_dotenv
import logging

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

def get_wp_auth():
    """Get WordPress authentication tuple."""
    return (WP_USERNAME, WP_APP_PASSWORD)

def verify_character_featured_images():
    """Fetch character posts and verify they have featured images."""
    logger.info("Verifying character posts have featured images...")

    # Fetch all character posts
    page = 1
    per_page = 100
    all_posts = []

    while True:
        posts_url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_character"
        params = {
            'per_page': per_page,
            'page': page,
            '_embed': 'wp:featuredmedia'  # Include featured media in response
        }
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
        total_pages = int(response.headers.get('X-WP-TotalPages', 1))
        if page > total_pages:
            break

    logger.info(f"Found {len(all_posts)} character posts")

    # Verify each post has a featured image or external thumbnail
    posts_with_featured = 0
    posts_without_featured = 0

    for post in all_posts:
        post_id = post['id']
        title = post.get('title', {}).get('rendered', f'Post {post_id}')
        featured_media = post.get('featured_media', 0)
        meta = post.get('meta', {})
        external_thumb = meta.get('_thumbnail_external_url', '')

        if featured_media and featured_media != 0:
            posts_with_featured += 1
            # Get media details if embedded
            embedded = post.get('_embedded', {})
            media_details = embedded.get('wp:featuredmedia', [])
            if media_details:
                media_url = media_details[0].get('source_url', 'N/A')
                logger.info(f"✅ {title} (ID: {post_id}) - Featured Image: {media_url}")
            else:
                logger.info(f"✅ {title} (ID: {post_id}) - Featured Image ID: {featured_media}")
        elif external_thumb:
            posts_with_featured += 1
            logger.info(f"✅ {title} (ID: {post_id}) - External Thumbnail: {external_thumb}")
        else:
            posts_without_featured += 1
            logger.warning(f"❌ {title} (ID: {post_id}) - No featured image or external thumbnail")

    logger.info(f"\nSummary:")
    logger.info(f"Posts with featured images: {posts_with_featured}")
    logger.info(f"Posts without featured images: {posts_without_featured}")
    logger.info(f"Total posts: {len(all_posts)}")

    return posts_with_featured == len(all_posts)

if __name__ == '__main__':
    success = verify_character_featured_images()
    if success:
        print("\n🎉 All character posts have featured images!")
    else:
        print("\n⚠️  Some character posts are missing featured images.")