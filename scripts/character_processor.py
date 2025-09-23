#!/usr/bin/env python3
"""
EVE Observer Character Processor
Handles processing of character-specific data.
"""

import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from config import *
from api_client import wp_request, send_email, fetch_esi, fetch_planet_details
from blueprint_processor import (
    update_blueprint_in_wp, extract_blueprints_from_assets, extract_blueprints_from_industry_jobs,
    update_blueprint_from_asset_in_wp
)
from data_processors import process_blueprints_parallel
from contract_processor import process_character_contracts

async def update_character_skills_in_wp(char_id: int, skills_data: Dict[str, Any]) -> None:
    """Update character post in WordPress with skills training data.
    
    Updates an existing character post with total skill points and last update timestamp.
    Only updates the skills metadata, preserving other character information.
    
    Args:
        char_id: EVE character ID
        skills_data: Skills data dictionary from ESI API containing 'total_sp' and other skill info
        
    Returns:
        None
        
    Note:
        Requires an existing character post to be present in WordPress.
        Logs success/failure of the update operation.
    """
    from api_client import wp_request
    
    slug = f"character-{char_id}"
    # Check if post exists by slug
    existing_posts = await wp_request('GET', f"/wp/v2/eve_character?slug={slug}")
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
        result = await wp_request('PUT', f"/wp/v2/eve_character/{post_id}", post_data)
        if result:
            logger.info(f"Updated skills for character {char_id}")
        else:
            logger.error(f"Failed to update skills for character {char_id}")

def check_industry_job_completions(jobs: List[Dict[str, Any]], char_name: str) -> None:
    """Check for upcoming industry job completions and prepare alerts.
    
    Scans active industry jobs for those completing within 24 hours and
    prepares email alerts (currently disabled). Jobs are checked for end_date
    within the next day from current time.
    
    Args:
        jobs: List of industry job dictionaries from ESI API
        char_name: Character name for alert personalization
        
    Returns:
        None
        
    Note:
        Email functionality is currently disabled in the code.
        Only logs the alert information instead of sending emails.
    """
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
    """Check for upcoming planet extraction pin completions and prepare alerts.
    
    Scans planetary interaction pins for those with expiry times within 24 hours
    and prepares email alerts (currently disabled). Extractions are checked for
    expiry_time within the next day from current time.
    
    Args:
        planet_details: Planet details dictionary containing 'pins' list from ESI API
        char_name: Character name for alert personalization
        
    Returns:
        None
        
    Note:
        Email functionality is currently disabled in the code.
        Only logs the alert information instead of sending emails.
    """
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

async def update_planet_in_wp(planet_id: int, planet_data: Dict[str, Any], char_id: int) -> None:
    """Update or create planet post in WordPress with planetary interaction data.
    
    Creates or updates WordPress posts for planets with PI installations.
    Includes pin count, planet details, and ownership information.
    
    Args:
        planet_id: EVE planet ID
        planet_data: Planet information dictionary from ESI API
        char_id: Character ID that owns/has access to this planet
        
    Returns:
        None
        
    Note:
        Stores complete planet details as JSON in post metadata.
        Updates existing posts or creates new ones as needed.
    """
    from api_client import wp_request
    
    slug = f"planet-{planet_id}"
    # Check if post exists by slug
    existing_posts = await wp_request('GET', f"/wp/v2/eve_planet?slug={slug}")
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
        result = await wp_request('PUT', f"/wp/v2/eve_planet/{post_id}", post_data)
    else:
        # Create new
        result = await wp_request('POST', "/wp/v2/eve_planet", post_data)

    if result:
        logger.info(f"Updated planet: {planet_id}")
    else:
        logger.error(f"Failed to update planet {planet_id}")

async def fetch_character_skills(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch character skills and training information from ESI.

    Retrieves the character's skill queue, trained skills, and total skill points.
    Used for tracking character progression and skill training status.

    Args:
        char_id: EVE character ID to fetch skills for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Skills data including total_sp and skills array.
    """
    endpoint = f"/characters/{char_id}/skills/"
    return await fetch_esi(endpoint, char_id, access_token)

async def fetch_character_blueprints(char_id, access_token):
    """
    Fetch character blueprint collection from ESI.

    Retrieves all blueprints owned by the character, including both BPOs and BPCs,
    with their ME/TE levels, location, and other blueprint attributes.

    Args:
        char_id: EVE character ID to fetch blueprints for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Blueprint data array if successful.
    """
    endpoint = f"/characters/{char_id}/blueprints/"
    return await fetch_esi(endpoint, char_id, access_token)

async def fetch_character_planets(char_id, access_token):
    """
    Fetch character planetary colony information from ESI.

    Retrieves data about the character's planetary colonies (PI), including
    planet types, colony status, and resource extraction setups.

    Args:
        char_id: EVE character ID to fetch planets for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Planetary colony data array if successful.
    """
    endpoint = f"/characters/{char_id}/planets/"
    return await fetch_esi(endpoint, char_id, access_token)

async def fetch_character_assets(char_id, access_token):
    """
    Fetch character assets from ESI.

    Retrieves the complete list of items owned by the character across all locations,
    including items in stations, structures, and ships.

    Args:
        char_id: EVE character ID to fetch assets for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Assets data array if successful.
    """
    endpoint = f"/characters/{char_id}/assets/"
    return await fetch_esi(endpoint, char_id, access_token)

async def fetch_character_industry_jobs(char_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch character industry jobs from ESI.

    Retrieves all active industry jobs for the character, including manufacturing,
    research, and other industry activities.

    Args:
        char_id: EVE character ID to fetch industry jobs for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Industry jobs data array if successful.
    """
    endpoint = f"/characters/{char_id}/industry/jobs/"
    return await fetch_esi(endpoint, char_id, access_token)

async def process_character_skills(char_id: int, access_token: str, char_name: str) -> None:
    """
    Process character skills data.

    Fetches character skills and total SP, then updates the character post
    in WordPress with the latest skills information.

    Args:
        char_id: Character ID to process skills for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
    """
    skills = await fetch_character_skills(char_id, access_token)
    if skills:
        # Update character with skills data
        await update_character_skills_in_wp(char_id, skills)
        logger.info(f"Skills for {char_name}: {skills['total_sp']} SP")

async def process_character_planets(char_id: int, access_token: str, char_name: str) -> None:
    """
    Process character planetary colony data.

    Fetches planetary colonies and retrieves detailed information for each,
    then updates planet posts in WordPress.

    Args:
        char_id: Character ID to process planets for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
    """
    planets = await fetch_character_planets(char_id, access_token)
    if planets:
        logger.info(f"Planets for {char_name}: {len(planets)} colonies")
        for planet in planets:
            planet_id = planet.get('planet_id')
            if planet_id:
                planet_details = await fetch_planet_details(char_id, planet_id, access_token)
                if planet_details:
                    await update_planet_in_wp(planet_id, planet_details, char_id)

async def process_character_data(char_id, token_data, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures, args):
    """
    Process data for a single character.

    Fetches and processes character-specific data including skills, blueprints
    from multiple sources, planetary colonies, and contracts.

    Args:
        char_id: Character ID to process.
        token_data: Token data dictionary for the character.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
        args: Parsed command line arguments.
    """
    access_token = token_data['access_token']
    char_name = token_data['name']

    logger.info(f"Fetching additional data for {char_name}...")

    # Fetch skills
    if args.all or args.skills:
        await process_character_skills(char_id, access_token, char_name)

    # Process character blueprints from all sources
    if args.all or args.blueprints:
        await process_character_blueprints(char_id, access_token, char_name, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures)

    # Process character planets
    if args.all or args.planets:
        await process_character_planets(char_id, access_token, char_name)

    # Process character contracts
    if args.all or args.contracts:
        await process_character_contracts(char_id, access_token, char_name, wp_post_id_cache, blueprint_cache, location_cache, structure_cache, failed_structures)

async def process_character_blueprints_from_endpoint(char_id: int, access_token: str, char_name: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process character blueprints from the direct blueprints endpoint.

    Fetches blueprints directly from the character's blueprint endpoint,
    filters to BPOs only, and processes them in parallel.

    Args:
        char_id: Character ID to fetch blueprints for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    logger.info(f"Fetching blueprints for {char_name}...")
    
    blueprints = await fetch_character_blueprints(char_id, access_token)
    if blueprints:
        # Filter to only BPOs (quantity == -1)
        bpo_blueprints = [bp for bp in blueprints if bp.get('quantity', 1) == -1]
        logger.info(f"Character blueprints: {len(blueprints)} total, {len(bpo_blueprints)} BPOs")
        if bpo_blueprints:
            # Process blueprints in parallel
            await process_blueprints_parallel(
                bpo_blueprints,
                update_blueprint_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

async def process_character_blueprints_from_assets(char_id: int, access_token: str, char_name: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process character blueprints from character assets.

    Extracts blueprints from character asset lists and processes them.

    Args:
        char_id: Character ID to fetch assets for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    char_assets = await fetch_character_assets(char_id, access_token)
    if char_assets:
        asset_blueprints = extract_blueprints_from_assets(char_assets, 'char', char_id, access_token)
        if asset_blueprints:
            logger.info(f"Character asset blueprints: {len(asset_blueprints)} items")
            # Process blueprints in parallel
            await process_blueprints_parallel(
                asset_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )

async def process_character_blueprints_from_industry_jobs(char_id: int, access_token: str, char_name: str, wp_post_id_cache: Dict[str, Any], blueprint_cache: Dict[str, Any], location_cache: Dict[str, Any], structure_cache: Dict[str, Any], failed_structures: Dict[str, Any]) -> None:
    """
    Process character blueprints from character industry jobs.

    Extracts blueprints from active character industry jobs and processes them.

    Args:
        char_id: Character ID to fetch industry jobs for.
        access_token: Valid access token for character data.
        char_name: Character name for logging.
        wp_post_id_cache: WordPress post ID cache.
        blueprint_cache: Blueprint name cache.
        location_cache: Location name cache.
        structure_cache: Structure name cache.
        failed_structures: Failed structure fetch cache.
    """
    jobs = await fetch_character_industry_jobs(char_id, access_token)
    if jobs:
        logger.info(f"Industry jobs for {char_name}: {len(jobs)} active")
        job_blueprints = extract_blueprints_from_industry_jobs(jobs, 'char', char_id)
        if job_blueprints:
            logger.info(f"Character industry job blueprints: {len(job_blueprints)} items")
            # Process blueprints in parallel
            await process_blueprints_parallel(
                job_blueprints,
                update_blueprint_from_asset_in_wp,
                wp_post_id_cache,
                char_id,
                access_token,
                blueprint_cache,
                location_cache,
                structure_cache,
                failed_structures
            )