#!/usr/bin/env python3
"""
Test script to verify higher quality images and external featured image field.
"""

import json
import os

import requests
from dotenv import load_dotenv

from config import WP_APP_PASSWORD, WP_BASE_URL, WP_USERNAME

# Load environment variables
load_dotenv()


def get_wp_auth():
    """Get WordPress authentication tuple."""
    return (WP_USERNAME, WP_APP_PASSWORD)


def test_character_portraits():
    """Test that character posts have higher quality portraits."""
    print("Testing character portraits...")

    # Get all character posts
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_character", auth=get_wp_auth(), params={"per_page": 100})
    if response.status_code != 200:
        print(f"Failed to fetch characters: {response.status_code}")
        return

    characters = response.json()
    print(f"Found {len(characters)} character posts")

    for char in characters:
        char_id = char.get("meta", {}).get("_eve_char_id")
        external_featured_url = char.get("meta", {}).get("_external_featured_image_url")
        thumbnail_external_url = char.get("meta", {}).get("_thumbnail_external_url")

        print(f"Character {char['title']['rendered']} (ID: {char_id}):")
        print(f"  External Featured Image: {external_featured_url}")
        print(f"  Thumbnail External: {thumbnail_external_url}")

        # Check if URL contains px256x256 for higher quality
        if thumbnail_external_url and "size=256" in thumbnail_external_url:
            print("  ✓ Higher quality portrait (256x256) using _thumbnail_external_url")
        elif external_featured_url and "size=256" in external_featured_url:
            print("  ✓ Higher quality portrait (256x256) using _external_featured_image_url")
        elif thumbnail_external_url:
            print("  ⚠ Lower quality portrait in _thumbnail_external_url")
        elif external_featured_url:
            print("  ⚠ Lower quality portrait in _external_featured_image_url")
        else:
            print("  ✗ No external featured image")

        print()


def test_blueprint_icons():
    """Test that blueprint posts have type icons."""
    print("Testing blueprint icons...")

    # Get a few blueprint posts
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint", auth=get_wp_auth(), params={"per_page": 10})
    if response.status_code != 200:
        print(f"Failed to fetch blueprints: {response.status_code}")
        return

    blueprints = response.json()
    print(f"Testing {len(blueprints)} blueprint posts")

    for bp in blueprints:
        bp_id = bp.get("meta", {}).get("_eve_bp_item_id")
        external_featured_url = bp.get("meta", {}).get("_external_featured_image_url")
        thumbnail_external_url = bp.get("meta", {}).get("_thumbnail_external_url")

        print(f"Blueprint {bp['title']['rendered']} (ID: {bp_id}):")
        print(f"  External Featured Image: {external_featured_url}")
        print(f"  Thumbnail External: {thumbnail_external_url}")

        # Check if URL contains size=128 for higher quality
        if external_featured_url and "size=128" in external_featured_url:
            print("  ✓ Higher quality icon (128x128)")
        elif external_featured_url:
            print("  ⚠ Lower quality icon")
        else:
            print("  ✗ No external featured image")

        print()


def test_corporation_logos():
    """Test that corporation posts have logos."""
    print("Testing corporation logos...")

    # Get corporation posts
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_corporation", auth=get_wp_auth(), params={"per_page": 10})
    if response.status_code != 200:
        print(f"Failed to fetch corporations: {response.status_code}")
        return

    corporations = response.json()
    print(f"Testing {len(corporations)} corporation posts")

    for corp in corporations:
        corp_id = corp.get("meta", {}).get("_eve_corp_id")
        external_featured_url = corp.get("meta", {}).get("_external_featured_image_url")
        thumbnail_external_url = corp.get("meta", {}).get("_thumbnail_external_url")

        print(f"Corporation {corp['title']['rendered']} (ID: {corp_id}):")
        print(f"  External Featured Image: {external_featured_url}")
        print(f"  Thumbnail External: {thumbnail_external_url}")

        # Check if URL contains size=128 for higher quality
        if external_featured_url and "size=128" in external_featured_url:
            print("  ✓ Higher quality logo (128x128)")
        elif external_featured_url:
            print("  ⚠ Lower quality logo")
        else:
            print("  ✗ No external featured image")

        print()


def test_planet_images():
    """Test that planet posts have renders."""
    print("Testing planet images...")

    # Get planet posts
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_planet", auth=get_wp_auth(), params={"per_page": 10})
    if response.status_code != 200:
        print(f"Failed to fetch planets: {response.status_code}")
        return

    planets = response.json()
    print(f"Testing {len(planets)} planet posts")

    for planet in planets:
        planet_id = planet.get("meta", {}).get("_eve_planet_id")
        external_featured_url = planet.get("meta", {}).get("_external_featured_image_url")
        thumbnail_external_url = planet.get("meta", {}).get("_thumbnail_external_url")

        print(f"Planet {planet['title']['rendered']} (ID: {planet_id}):")
        print(f"  External Featured Image: {external_featured_url}")
        print(f"  Thumbnail External: {thumbnail_external_url}")

        # Check if URL contains size=512 for higher quality
        if external_featured_url and "size=512" in external_featured_url:
            print("  ✓ Higher quality render (512x512)")
        elif external_featured_url:
            print("  ⚠ Lower quality render")
        else:
            print("  ✗ No external featured image")

        print()


if __name__ == "__main__":
    print("Testing higher quality images and external featured image field...\n")

    test_character_portraits()
    test_blueprint_icons()
    test_corporation_logos()
    test_planet_images()

    print("Test completed!")
