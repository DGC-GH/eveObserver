import requests
import os
from dotenv import load_dotenv

load_dotenv()

WP_BASE_URL = os.getenv('WP_URL')
WP_USERNAME = os.getenv('WP_USERNAME')
WP_APP_PASSWORD = os.getenv('WP_APP_PASSWORD')

def get_wp_auth():
    return (WP_USERNAME, WP_APP_PASSWORD)

# Fetch all blueprint posts with pagination
posts = []
page = 1
while True:
    response = requests.get(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint?per_page=100&page={page}", auth=get_wp_auth())
    if response.status_code != 200:
        break
    page_posts = response.json()
    if not page_posts:
        break
    posts.extend(page_posts)
    page += 1

# Group by item_id
from collections import defaultdict
grouped = defaultdict(list)
for post in posts:
    slug = post['slug']
    if slug.startswith('blueprint-'):
        # Extract item_id from slug
        parts = slug.split('-')
        if len(parts) >= 2:
            item_id = parts[1]
            if item_id.isdigit():
                grouped[item_id].append(post)

# For each item_id, keep only the one with correct slug, delete others
for item_id, posts_list in grouped.items():
    correct_slug = f"blueprint-{item_id}"
    correct_post = None
    to_delete = []
    for post in posts_list:
        if post['slug'] == correct_slug:
            correct_post = post
        else:
            to_delete.append(post)
    
    if correct_post:
        for post in to_delete:
            print(f"Deleting duplicate post ID {post['id']} with slug {post['slug']}")
            delete_response = requests.delete(f"{WP_BASE_URL}/wp-json/wp/v2/eve_blueprint/{post['id']}?force=true", auth=get_wp_auth())
            if delete_response.status_code == 200:
                print(f"Deleted post {post['id']}")
            else:
                print(f"Failed to delete post {post['id']}: {delete_response.status_code}")
    else:
        print(f"No correct post for item_id {item_id}, keeping all? Wait, this shouldn't happen.")

print("Cleanup complete.")