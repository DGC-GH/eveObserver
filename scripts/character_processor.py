#!/usr/bin/env python3
"""
EVE Observer Character Processor
Handles processing of character-specific data.
"""

import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from config import *
from api_client import wp_request, send_email

def update_character_skills_in_wp(char_id: int, skills_data: Dict[str, Any]) -> None:
    """Update character post with skills data."""
    slug = f"character-{char_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_character?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    if existing_post:
        post_id = existing_post['id']
        # Update with skills data
        post_data = {
            'meta': {
                '_eve_total_sp': skills_data.get('total_sp', 0),
                '_eve_last_updated': datetime.now(timezone.utc).isoformat()
            }
        }
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_character/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
        if response.status_code in [200, 201]:
            logger.info(f"Updated skills for character {char_id}")
        else:
            logger.error(f"Failed to update skills for character {char_id}: {response.status_code} - {response.text}")

def check_industry_job_completions(jobs: List[Dict[str, Any]], char_name: str) -> None:
    """Check for upcoming industry job completions and send alerts."""
    now = datetime.now(timezone.utc)
    upcoming_completions = [
        job for job in jobs
        if 'end_date' in job and 
        now <= datetime.fromisoformat(job['end_date'].replace('Z', '+00:00')) <= now + timedelta(hours=24)
    ]

    if upcoming_completions:
        subject = f"EVE Alert: {len(upcoming_completions)} industry jobs ending soon for {char_name}"
        body = f"The following jobs will complete within 24 hours:\n\n"
        for job in upcoming_completions:
            body += f"- Job ID {job['job_id']}: {job.get('activity_id', 'Unknown')} ending {job['end_date']}\n"
        # Email functionality disabled
        logger.info(f"Email alert disabled: {subject}")
        # send_email(subject, body)

def check_planet_extraction_completions(planet_details: Dict[str, Any], char_name: str) -> None:
    """Check for upcoming planet extraction completions and send alerts."""
    now = datetime.now(timezone.utc)
    upcoming_extractions = [
        pin for pin in planet_details.get('pins', [])
        if 'expiry_time' in pin and 
        now <= datetime.fromisoformat(pin['expiry_time'].replace('Z', '+00:00')) <= now + timedelta(hours=24)
    ]
    
    if upcoming_extractions:
        subject = f"EVE Alert: {len(upcoming_extractions)} planet extractions ending soon for {char_name}"
        body = f"The following extractions will complete within 24 hours:\n\n"
        for pin in upcoming_extractions:
            body += f"- Pin ID {pin['pin_id']}: {pin.get('type_id', 'Unknown')} ending {pin['expiry_time']}\n"
        # Email functionality disabled
        logger.info(f"Email alert disabled: {subject}")
        # send_email(subject, body)

def update_planet_in_wp(planet_id: int, planet_data: Dict[str, Any], char_id: int) -> None:
    """Update or create planet post in WordPress."""
    slug = f"planet-{planet_id}"
    # Check if post exists by slug
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_planet?slug={slug}", auth=get_wp_auth())
    existing_posts = response.json() if response.status_code == 200 else []
    existing_post = existing_posts[0] if existing_posts else None

    post_data = {
        'title': f"Planet {planet_id}",
        'slug': slug,
        'status': 'publish',
        'meta': {
            '_eve_planet_id': planet_id,
            '_eve_char_id': char_id,
            '_eve_planet_type': planet_data.get('type_id'),
            '_eve_planet_name': planet_data.get('name'),
            '_eve_planet_solar_system_id': planet_data.get('solar_system_id'),
            '_eve_last_updated': datetime.now(timezone.utc).isoformat()
        }
    }

    # Add planet details if available
    if 'pins' in planet_data:
        post_data['meta']['_eve_planet_pins'] = len(planet_data['pins'])
        post_data['meta']['_eve_planet_details'] = str(planet_data)

    if existing_post:
        # Update existing
        post_id = existing_post['id']
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_planet/{post_id}"
        response = requests.put(url, json=post_data, auth=get_wp_auth())
    else:
        # Create new
        url = f"{WP_BASE_URL}/wp-json/wp/v2/eve_planet"
        response = requests.post(url, json=post_data, auth=get_wp_auth())

    if response.status_code in [200, 201]:
        logger.info(f"Updated planet: {planet_id}")
    else:
        logger.error(f"Failed to update planet {planet_id}: {response.status_code} - {response.text}")