"""
EVE Observer Configuration
Centralized configuration for the EVE Observer application.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# API Configuration
ESI_BASE_URL = 'https://esi.evetech.net/latest'
ESI_TIMEOUT = int(os.getenv('ESI_TIMEOUT', 30))
ESI_MAX_RETRIES = int(os.getenv('ESI_MAX_RETRIES', 3))
ESI_MAX_WORKERS = int(os.getenv('ESI_MAX_WORKERS', 3))

# WordPress Configuration
WP_BASE_URL = os.getenv('WP_URL')
WP_USERNAME = os.getenv('WP_USERNAME')
WP_APP_PASSWORD = os.getenv('WP_APP_PASSWORD')
WP_PER_PAGE = int(os.getenv('WP_PER_PAGE', 100))

# Cache Configuration
CACHE_DIR = os.getenv('CACHE_DIR', 'cache')
BLUEPRINT_CACHE_FILE = os.path.join(CACHE_DIR, 'blueprint_names.json')
LOCATION_CACHE_FILE = os.path.join(CACHE_DIR, 'location_names.json')
STRUCTURE_CACHE_FILE = os.path.join(CACHE_DIR, 'structure_names.json')
FAILED_STRUCTURES_FILE = os.path.join(CACHE_DIR, 'failed_structures.json')
WP_POST_ID_CACHE_FILE = os.path.join(CACHE_DIR, 'wp_post_ids.json')
TOKENS_FILE = os.path.join(os.path.dirname(__file__), 'esi_tokens.json')

# Email Configuration
EMAIL_SMTP_SERVER = os.getenv('EMAIL_SMTP_SERVER')
EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', 587))
EMAIL_USERNAME = os.getenv('EMAIL_USERNAME')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_FROM = os.getenv('EMAIL_FROM')
EMAIL_TO = os.getenv('EMAIL_TO')

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'eve_observer.log')

# Corporation Filter
ALLOWED_CORPORATIONS = ['no mercy incorporated']  # Case insensitive

# Rate Limiting
RATE_LIMIT_BUFFER = 1  # seconds to add as buffer for rate limits