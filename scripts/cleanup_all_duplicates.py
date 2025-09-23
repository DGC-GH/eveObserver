import os

import requests
from dotenv import load_dotenv

load_dotenv()

WP_BASE_URL = os.getenv("WP_URL")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")


def get_wp_auth():
    return (WP_USERNAME, WP_APP_PASSWORD)


post_types = ["eve_character", "eve_blueprint", "eve_planet"]

for post_type in post_types:
    print(f"Cleaning up {post_type}...")
    # Fetch all posts with pagination
    posts = []
    page = 1
    while True:
        response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/{post_type}?per_page=100&page={page}", auth=get_wp_auth())
        if response.status_code != 200:
            break
        page_posts = response.json()
        if not page_posts:
            break
        posts.extend(page_posts)
        page += 1

    # Group by base slug
    from collections import defaultdict

    grouped = defaultdict(list)
    for post in posts:
        slug = post["slug"]
        if post_type == "eve_character" and slug.startswith("character-"):
            # Extract base slug, remove -number
            parts = slug.split("-")
            if len(parts) == 2 or (len(parts) == 3 and parts[2].isdigit()):
                base_slug = f"character-{parts[1]}"
            else:
                base_slug = slug
        elif post_type == "eve_blueprint" and slug.startswith("blueprint-"):
            parts = slug.split("-")
            if len(parts) >= 2:
                base_slug = f"blueprint-{parts[1]}"
        elif post_type == "eve_planet" and slug.startswith("planet-"):
            base_slug = slug
        else:
            continue
        grouped[base_slug].append(post)

    # For each base_slug, keep only the one with the exact slug, delete others
    for base_slug, posts_list in grouped.items():
        correct_post = None
        to_delete = []
        for post in posts_list:
            if post["slug"] == base_slug:
                correct_post = post
            else:
                to_delete.append(post)

        if correct_post:
            for post in to_delete:
                print(f"Deleting duplicate post ID {post['id']} with slug {post['slug']}")
                delete_response = requests.delete(
                    f"{WP_BASE_URL}/wp-json/wp/v2/{post_type}/{post['id']}?force=true", auth=get_wp_auth()
                )
                if delete_response.status_code == 200:
                    print(f"Deleted post {post['id']}")
                else:
                    print(f"Failed to delete post {post['id']}: {delete_response.status_code}")
        else:
            print(f"No correct post for {base_slug}, keeping all? This shouldn't happen.")

print("Cleanup complete.")
