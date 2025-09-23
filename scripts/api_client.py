#!/usr/bin/env python3
"""
EVE Observer API Client
Handles ESI API and WordPress REST API interactions.
"""

import os
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
import logging
import requests
from typing import Any, Dict, List, Optional, Callable, Awaitable
import re
from dataclasses import dataclass
from enum import Enum
import time
import functools
from config import *

# Performance benchmarking decorator
def benchmark(func):
    """Decorator to measure and log function execution time."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info(f"{func.__name__} completed in {elapsed:.3f}s")
        return result
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info(f"{func.__name__} completed in {elapsed:.3f}s")
        return result
    
    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

# Circuit Breaker implementation for better error handling
class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5  # Number of failures before opening
    recovery_timeout: int = 60  # Seconds to wait before trying half-open
    success_threshold: int = 3  # Number of successes needed to close circuit
    timeout: float = 30.0       # Request timeout in seconds

class CircuitBreaker:
    """Circuit breaker pattern implementation for API calls."""
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        
    def _should_attempt_call(self) -> bool:
        """Determine if we should attempt the API call."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if self._is_recovery_timeout_expired():
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                logger.info(f"Circuit breaker {self.name} entering HALF_OPEN state")
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True
        return False
    
    def _is_recovery_timeout_expired(self) -> bool:
        """Check if enough time has passed to try recovery."""
        if self.last_failure_time is None:
            return True
        return (time.time() - self.last_failure_time) >= self.config.recovery_timeout
    
    def _record_success(self):
        """Record a successful call."""
        self.failure_count = 0
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                logger.info(f"Circuit breaker {self.name} CLOSED after {self.success_count} successes")
    
    def _record_failure(self):
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.success_count = 0
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker {self.name} OPEN due to failure in HALF_OPEN state")
        elif (self.state == CircuitBreakerState.CLOSED and 
              self.failure_count >= self.config.failure_threshold):
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker {self.name} OPEN after {self.failure_count} failures")
    
    async def call(self, func: Callable[..., Awaitable], *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if not self._should_attempt_call():
            raise ESIRequestError(f"Circuit breaker {self.name} is OPEN")
        
        try:
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.config.timeout)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise e

# Global circuit breakers for different API endpoints
_esi_circuit_breaker = CircuitBreaker("ESI_API", CircuitBreakerConfig(
    failure_threshold=5,
    recovery_timeout=60,
    success_threshold=3,
    timeout=30.0
))

_wp_circuit_breaker = CircuitBreaker("WordPress_API", CircuitBreakerConfig(
    failure_threshold=3,
    recovery_timeout=30,
    success_threshold=2,
    timeout=15.0
))

# Custom exceptions for better error handling

# Custom exceptions for better error handling
class ESIApiError(Exception):
    """Base exception for ESI API errors."""
    pass

class ESIAuthError(ESIApiError):
    """Exception raised for authentication failures."""
    pass

class ESIRequestError(ESIApiError):
    """Exception raised for general ESI request errors."""
    pass

class WordPressApiError(Exception):
    """Base exception for WordPress API errors."""
    pass

class WordPressAuthError(WordPressApiError):
    """Exception raised for WordPress authentication failures."""
    pass

class WordPressRequestError(WordPressApiError):
    """Exception raised for general WordPress request errors."""
    pass

@dataclass
class ApiConfig:
    """Centralized configuration for API settings and limits."""
    esi_base_url: str = 'https://esi.evetech.net/latest'
    esi_timeout: int = 30
    esi_max_retries: int = 3
    esi_max_workers: int = 10
    wp_per_page: int = 100
    rate_limit_buffer: int = 1

    @classmethod
    def from_env(cls) -> 'ApiConfig':
        """Create ApiConfig instance from environment variables."""
        return cls(
            esi_base_url=os.getenv('ESI_BASE_URL', 'https://esi.evetech.net/latest'),
            esi_timeout=int(os.getenv('ESI_TIMEOUT', 30)),
            esi_max_retries=int(os.getenv('ESI_MAX_RETRIES', 3)),
            esi_max_workers=int(os.getenv('ESI_MAX_WORKERS', 10)),
            wp_per_page=int(os.getenv('WP_PER_PAGE', 100)),
        )

load_dotenv()

# Create a global aiohttp session for connection reuse
session = None
_session_cleanup_registered = False

async def get_session():
    """Get or create aiohttp session with proper cleanup registration."""
    global session, _session_cleanup_registered
    if session is None or session.closed:
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=api_config.esi_timeout),
            connector=aiohttp.TCPConnector(limit=api_config.esi_max_workers * 2)
        )
        # Register cleanup only once
        if not _session_cleanup_registered:
            import atexit
            atexit.register(_sync_cleanup_session)
            _session_cleanup_registered = True
    return session

def _sync_cleanup_session():
    """Synchronous cleanup wrapper for the global session."""
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, we can't await, so just close synchronously if possible
            if session and not session.closed:
                # This is not ideal but prevents the error
                logger.warning("Session cleanup attempted while event loop is running")
        else:
            # Create a new task to cleanup
            loop.run_until_complete(_cleanup_session())
    except RuntimeError:
        # No event loop, try synchronous cleanup
        logger.warning("No event loop available for session cleanup")

async def _cleanup_session():
    """Cleanup the global session."""
    global session
    if session and not session.closed:
        await session.close()
        session = None

# Initialize API configuration
api_config = ApiConfig.from_env()

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

@benchmark
async def _fetch_esi_with_retry(endpoint: str, headers: Optional[Dict[str, str]] = None, max_retries: int = None, is_public: bool = True) -> Dict[str, Any]:
    """Internal function to fetch data from ESI API with circuit breaker and error handling."""
    
    async def _do_request():
        nonlocal max_retries
        start_time = time.time()
        if max_retries is None:
            max_retries = api_config.esi_max_retries

        sess = await get_session()
        url = f"{api_config.esi_base_url}{endpoint}"

        for attempt in range(max_retries):
            try:
                async with sess.get(url, headers=headers or {}) as response:
                    if response.status == 200:
                        result = await response.json()
                        elapsed = time.time() - start_time
                        endpoint_type = "public" if is_public else "authenticated"
                        logger.info(f"ESI {endpoint_type} fetch successful: {endpoint} in {elapsed:.2f}s")
                        return result
                    elif response.status == 401 and not is_public:
                        elapsed = time.time() - start_time
                        logger.error(f"Authentication failed for endpoint {endpoint} in {elapsed:.2f}s")
                        raise ESIAuthError(f"Authentication failed: {endpoint}")
                    elif response.status == 403 and not is_public:
                        elapsed = time.time() - start_time
                        logger.error(f"Access forbidden for endpoint {endpoint} in {elapsed:.2f}s")
                        raise ESIRequestError(f"Access forbidden: {endpoint}")
                    elif response.status == 404:
                        elapsed = time.time() - start_time
                        endpoint_type = "public" if is_public else ""
                        logger.warning(f"Resource not found for {endpoint_type} endpoint {endpoint} in {elapsed:.2f}s")
                        raise ESIRequestError(f"Resource not found: {endpoint}")
                    elif response.status == 429:  # Rate limited
                        # Check for X-ESI-Error-Limit-Remain header
                        error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                        error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                        if error_limit_reset:
                            wait_time = int(error_limit_reset) + 1  # Add 1 second buffer
                            endpoint_type = "public" if is_public else ""
                            logger.info(f"RATE LIMIT: Waiting {wait_time} seconds for {endpoint_type} endpoint...")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            # Fallback: wait 60 seconds if no reset header
                            endpoint_type = "public" if is_public else ""
                            logger.info(f"RATE LIMIT: Waiting 60 seconds for {endpoint_type} endpoint (no reset header)...")
                            await asyncio.sleep(60)
                            continue
                    elif response.status == 420:  # Error limited
                        error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                        error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                        if error_limit_reset:
                            wait_time = int(error_limit_reset) + 1
                            endpoint_type = "public" if is_public else ""
                            logger.info(f"ERROR LIMIT: Waiting {wait_time} seconds for {endpoint_type} endpoint...")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            endpoint_type = "public" if is_public else ""
                            logger.info(f"ERROR LIMIT: Waiting 60 seconds for {endpoint_type} endpoint...")
                            await asyncio.sleep(60)
                            continue
                    elif response.status >= 500:
                        # Server error, retry
                        if attempt < max_retries - 1:
                            wait_time = 2 ** attempt  # Exponential backoff
                            logger.warning(f"SERVER ERROR {response.status}: Retrying in {wait_time} seconds...")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"SERVER ERROR {response.status}: Max retries exceeded")
                            raise ESIRequestError(f"Server error after {max_retries} retries: {endpoint}")
                    else:
                        elapsed = time.time() - start_time
                        logger.error(f"ESI API error for {endpoint}: {response.status} - {await response.text()} (took {elapsed:.2f}s)")
                        raise ESIRequestError(f"ESI API error {response.status}: {endpoint}")

            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"TIMEOUT: Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    elapsed = time.time() - start_time
                    logger.error(f"TIMEOUT: Max retries exceeded for {endpoint} (took {elapsed:.2f}s)")
                    raise ESIRequestError(f"Timeout after {max_retries} retries: {endpoint}")
            except aiohttp.ClientError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"NETWORK ERROR: {e}. Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    elapsed = time.time() - start_time
                    logger.error(f"NETWORK ERROR: {e}. Max retries exceeded for {endpoint} (took {elapsed:.2f}s)")
                    raise ESIRequestError(f"Network error after {max_retries} retries: {endpoint}")

        elapsed = time.time() - start_time
        endpoint_type = "public" if is_public else "authenticated"
        raise ESIRequestError(f"Max retries exceeded for {endpoint_type} endpoint: {endpoint} (took {elapsed:.2f}s)")
    
    # Use circuit breaker to protect the API call
    return await _esi_circuit_breaker.call(_do_request)

async def fetch_public_esi(endpoint: str, max_retries: int = None) -> Optional[Dict[str, Any]]:
    """Fetch data from ESI API (public endpoints, no auth) with rate limiting and error handling."""
    return await _fetch_esi_with_retry(endpoint, headers=None, max_retries=max_retries, is_public=True)

async def fetch_esi(endpoint: str, char_id: Optional[int], access_token: str, max_retries: int = None) -> Optional[Dict[str, Any]]:
    """Fetch data from ESI API with rate limiting and error handling."""
    headers = {'Authorization': f'Bearer {access_token}'}
    return await _fetch_esi_with_retry(endpoint, headers=headers, max_retries=max_retries, is_public=False)

@benchmark
async def wp_request(method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
    """Make async request to WordPress REST API with circuit breaker protection."""
    
    async def _do_wp_request():
        start_time = time.time()
        sess = await get_session()
        url = f"{WP_BASE_URL}{endpoint}"
        auth = aiohttp.BasicAuth(WP_USERNAME, WP_APP_PASSWORD)

        try:
            if method.upper() == 'GET':
                async with sess.get(url, auth=auth) as response:
                    if response.status == 200:
                        result = await response.json()
                        elapsed = time.time() - start_time
                        logger.info(f"WordPress GET successful: {endpoint} in {elapsed:.2f}s")
                        return result
                    elif response.status == 401:
                        elapsed = time.time() - start_time
                        logger.error(f"WordPress authentication failed: {response.status} - {await response.text()} (took {elapsed:.2f}s)")
                        raise WordPressAuthError(f"Authentication failed for {endpoint}")
                    else:
                        elapsed = time.time() - start_time
                        logger.error(f"WordPress API error: {response.status} - {await response.text()} (took {elapsed:.2f}s)")
                        raise WordPressRequestError(f"WordPress API error {response.status}: {endpoint}")
            elif method.upper() == 'POST':
                async with sess.post(url, json=data, auth=auth) as response:
                    if response.status in [200, 201]:
                        result = await response.json()
                        elapsed = time.time() - start_time
                        logger.info(f"WordPress POST successful: {endpoint} in {elapsed:.2f}s")
                        return result
                    elif response.status == 401:
                        elapsed = time.time() - start_time
                        logger.error(f"WordPress authentication failed: {response.status} - {await response.text()} (took {elapsed:.2f}s)")
                        raise WordPressAuthError(f"Authentication failed for {endpoint}")
                    else:
                        elapsed = time.time() - start_time
                        logger.error(f"WordPress API error: {response.status} - {await response.text()} (took {elapsed:.2f}s)")
                        raise WordPressRequestError(f"WordPress API error {response.status}: {endpoint}")
            elif method.upper() == 'PUT':
                async with sess.put(url, json=data, auth=auth) as response:
                    if response.status in [200, 201]:
                        result = await response.json()
                        elapsed = time.time() - start_time
                        logger.info(f"WordPress PUT successful: {endpoint} in {elapsed:.2f}s")
                        return result
                    elif response.status == 401:
                        elapsed = time.time() - start_time
                        logger.error(f"WordPress authentication failed: {response.status} - {await response.text()} (took {elapsed:.2f}s)")
                        raise WordPressAuthError(f"Authentication failed for {endpoint}")
                    else:
                        elapsed = time.time() - start_time
                        logger.error(f"WordPress API error: {response.status} - {await response.text()} (took {elapsed:.2f}s)")
                        raise WordPressRequestError(f"WordPress API error {response.status}: {endpoint}")
            elif method.upper() == 'DELETE':
                params = {'force': 'true'} if data and data.get('force') else None
                async with sess.delete(url, auth=auth, params=params) as response:
                    if response.status == 200:
                        elapsed = time.time() - start_time
                        logger.info(f"WordPress DELETE successful: {endpoint} in {elapsed:.2f}s")
                        return {"deleted": True}
                    elif response.status == 401:
                        elapsed = time.time() - start_time
                        logger.error(f"WordPress authentication failed: {response.status} - {await response.text()} (took {elapsed:.2f}s)")
                        raise WordPressAuthError(f"Authentication failed for {endpoint}")
                    else:
                        elapsed = time.time() - start_time
                        logger.error(f"WordPress API error: {response.status} - {await response.text()} (took {elapsed:.2f}s)")
                        raise WordPressRequestError(f"WordPress API error {response.status}: {endpoint}")
        except aiohttp.ClientError as e:
            elapsed = time.time() - start_time
            logger.error(f"WordPress API request failed: {e} (took {elapsed:.2f}s)")
            raise WordPressRequestError(f"Network error for WordPress API: {endpoint}")

        return None
    
    # Use circuit breaker to protect WordPress API calls
    return await _wp_circuit_breaker.call(_do_wp_request)

def send_email(subject: str, body: str) -> None:
    """Send an email alert."""
    if not all([EMAIL_SMTP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO]):
        logger.warning("Email configuration incomplete, skipping alert.")
        return

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO

    try:
        server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        server.quit()
        logger.info(f"Alert email sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

def refresh_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Refresh an access token."""
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    client_id = os.getenv('ESI_CLIENT_ID')
    client_secret = os.getenv('ESI_CLIENT_SECRET')
    response = requests.post('https://login.eveonline.com/v2/oauth/token', data=data, auth=(client_id, client_secret))
    if response.status_code == 200:
        token_data = response.json()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data['expires_in'])
        return {
            'access_token': token_data['access_token'],
            'refresh_token': token_data.get('refresh_token', refresh_token),
            'expires_at': expires_at.isoformat()
        }
    else:
        logger.error(f"Failed to refresh token: {response.status_code} - {response.text}")
        return None

@benchmark
async def fetch_type_icon(type_id: int, size: int = 512) -> str:
    """Fetch type icon URL from images.evetech.net with fallback."""
    # Try the 'bp' variation first for blueprints, then fallback to regular icon
    variations = ['bp', 'icon']

    sess = await get_session()
    for variation in variations:
        icon_url = f"https://images.evetech.net/types/{type_id}/{variation}?size={size}"
        # Test if the URL exists by making a HEAD request
        try:
            async with sess.head(icon_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    return icon_url
        except:
            continue

    # If no icon found, return placeholder
    return f"https://via.placeholder.com/{size}x{size}/cccccc/000000?text=No+Icon"

def sanitize_string(value: str) -> str:
    return re.sub(r'[^\w\s\-.,]', '', value) if isinstance(value, str) else str(value)