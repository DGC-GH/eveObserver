#!/usr/bin/env python3
"""
EVE Observer Corporation Processor
Handles processing of corporation-specific data.
"""

import requests
from datetime import datetime, timezone
from typing import Dict, Any
from config import *

def update_corporation_in_wp(corp_id: int, corp_data: Dict[str, Any]) -> None:
    """Update or create corporation post in WordPress with corporation details.
    
    Creates or updates WordPress posts for EVE corporations with comprehensive
    metadata including member count, CEO, alliance affiliation, and other details.
    
    Args:
        corp_id: EVE corporation ID
        corp_data: Corporation information dictionary from ESI API
        
    Returns:
        None
        
    Note:
        Stores corporation details as post metadata in WordPress.
        Removes null values from metadata to avoid WordPress validation issues.
        Updates existing posts or creates new ones based on slug lookup.
    """
    slug = f"corporation-{corp_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    post_data = {
        'title': corp_data.get('name', f'Corporation {corp_id}'),
        'slug': slug,
        'status': 'publish',
        'meta': {
            '_eve_corp_id': corp_id,
            '_eve_corp_name': corp_data.get('name'),
            '_eve_corp_ticker': corp_data.get('ticker'),
            '_eve_corp_member_count': corp_data.get('member_count'),
            '_eve_corp_ceo_id': corp_data.get('ceo_id'),
            '_eve_corp_alliance_id': corp_data.get('alliance_id'),
            '_eve_corp_date_founded': corp_data.get('date_founded'),
            '_eve_corp_tax_rate': corp_data.get('tax_rate'),
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Remove null values
    post_data['meta'] = {k: v for k, v in post_data['meta'].items() if v is not None}

    if existing_post:
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        logger.info(f"Updated corporation: {corp_data.get('name', corp_id)}")
    else:
        logger.error(f"Failed to update corporation {corp_id}: {response.status_code} - {response.text}")