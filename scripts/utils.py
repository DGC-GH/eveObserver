#!/usr/bin/env python3
"""
EVE Observer Utilities
Shared utility functions for the EVE Observer application.
"""

import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

import requests

from config import *

logger = logging.getLogger(__name__)


def send_email(subject: str, body: str) -> None:
    """
    Send an email notification.

    Sends an email using the configured SMTP server with the provided subject and body.
    Requires EMAIL_* environment variables to be configured.

    Args:
        subject: Email subject line.
        body: Email body content (plain text).

    Note:
        Silently fails if email configuration is incomplete or sending fails.
        Used for contract outbid notifications and system alerts.
    """
    if not all([EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO]):
        logger.warning("Email configuration incomplete, skipping email send")
        return

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO

        server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        server.quit()
        logger.info(f"Email sent successfully: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")


def get_region_from_location(location_id: int) -> Optional[int]:
    """
    Get region_id from a location_id (station or structure) with caching.

    Resolves location IDs to region IDs by traversing the EVE universe hierarchy:
    location -> solar system -> constellation -> region.

    Args:
        location_id: Station or structure location ID.

    Returns:
        Optional[int]: Region ID if found, None otherwise.

    Note:
        Uses caching to avoid repeated API calls. Handles both station
        and structure location types differently.
    """
    if not location_id:
        return None

    # Load cache
    cache_file = "cache/region_cache.json"
    try:
        with open(cache_file, "r") as f:
            region_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        region_cache = {}

    location_id_str = str(location_id)
    if location_id_str in region_cache:
        return region_cache[location_id_str]

    region_id = None
    if location_id >= 1000000000000:  # Structure
        # For structures, we need to fetch structure info to get solar_system_id, then region
        try:
            response = requests.get(
                f"{ESI_BASE_URL}/universe/structures/{location_id}", headers={"Accept": "application/json"}, timeout=30
            )
            response.raise_for_status()
            struct_data = response.json()
        except requests.exceptions.RequestException:
            struct_data = None

        if struct_data:
            solar_system_id = struct_data.get("solar_system_id")
            if solar_system_id:
                try:
                    response = requests.get(
                        f"{ESI_BASE_URL}/universe/systems/{solar_system_id}",
                        headers={"Accept": "application/json"},
                        timeout=30,
                    )
                    response.raise_for_status()
                    system_data = response.json()
                except requests.exceptions.RequestException:
                    system_data = None

                if system_data:
                    constellation_id = system_data.get("constellation_id")
                    if constellation_id:
                        try:
                            response = requests.get(
                                f"{ESI_BASE_URL}/universe/constellations/{constellation_id}",
                                headers={"Accept": "application/json"},
                                timeout=30,
                            )
                            response.raise_for_status()
                            constellation_data = response.json()
                        except requests.exceptions.RequestException:
                            constellation_data = None

                        if constellation_data:
                            region_id = constellation_data.get("region_id")
    else:  # Station
        try:
            response = requests.get(
                f"{ESI_BASE_URL}/universe/stations/{location_id}", headers={"Accept": "application/json"}, timeout=30
            )
            response.raise_for_status()
            station_data = response.json()
        except requests.exceptions.RequestException:
            station_data = None

        if station_data:
            system_id = station_data.get("system_id")
            if system_id:
                try:
                    response = requests.get(
                        f"{ESI_BASE_URL}/universe/systems/{system_id}",
                        headers={"Accept": "application/json"},
                        timeout=30,
                    )
                    response.raise_for_status()
                    system_data = response.json()
                except requests.exceptions.RequestException:
                    system_data = None

                if system_data:
                    constellation_id = system_data.get("constellation_id")
                    if constellation_id:
                        try:
                            response = requests.get(
                                f"{ESI_BASE_URL}/universe/constellations/{constellation_id}",
                                headers={"Accept": "application/json"},
                                timeout=30,
                            )
                            response.raise_for_status()
                            constellation_data = response.json()
                        except requests.exceptions.RequestException:
                            constellation_data = None

                        if constellation_data:
                            region_id = constellation_data.get("region_id")

    # Cache the result
    if region_id:
        region_cache[location_id_str] = region_id
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(region_cache, f, indent=2)

    return region_id
