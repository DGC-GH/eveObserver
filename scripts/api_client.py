#!/usr/bin/env python3
"""
EVE Observer API Client
Handles ESI API and WordPress REST API interactions.
"""

import asyncio
import functools
import logging
import os
import re
import smtplib
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp
import requests
from dotenv import load_dotenv

from config import (
    EMAIL_FROM,
    EMAIL_PASSWORD,
    EMAIL_SMTP_PORT,
    EMAIL_SMTP_SERVER,
    EMAIL_TO,
    EMAIL_USERNAME,
    ESI_BASE_URL,
    LOG_FILE,
    LOG_LEVEL,
    WP_APP_PASSWORD,
    WP_BASE_URL,
    WP_USERNAME,
)


# Performance benchmarking decorator
def benchmark(func):
    """Decorator to measure and log function execution time."""

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        performance_logger.info(f"{func.__name__} completed in {elapsed:.3f}s")
        return result

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        performance_logger.info(f"{func.__name__} completed in {elapsed:.3f}s")
        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


# Input validation decorators
def validate_api_response(func):
    """
    Decorator to validate API response data.

    Checks for common issues like None responses, empty data,
    and ensures response is a dictionary when expected.
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)

        if result is None:
            logger.warning(f"{func.__name__} returned None - possible API failure")
            return result

        if isinstance(result, dict):
            if not result:
                logger.warning(f"{func.__name__} returned empty dictionary")
            # Validate common EVE API response patterns
            elif "error" in result:
                logger.error(f"{func.__name__} returned error response: {result['error']}")
            elif "message" in result and "error" in result.get("message", "").lower():
                logger.error(f"{func.__name__} returned error message: {result['message']}")

        return result

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        result = func(*args, **kwargs)

        if result is None:
            logger.warning(f"{func.__name__} returned None - possible API failure")
            return result

        if isinstance(result, dict):
            if not result:
                logger.warning(f"{func.__name__} returned empty dictionary")
            elif "error" in result:
                logger.error(f"{func.__name__} returned error response: {result['error']}")
            elif "message" in result and "error" in result.get("message", "").lower():
                logger.error(f"{func.__name__} returned error message: {result['message']}")

        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


def validate_input_params(*param_types):
    """
    Decorator to validate input parameter types.

    Args:
        *param_types: Expected types for positional arguments (excluding self/cls)
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Skip 'self' or 'cls' for methods/classmethods
            start_idx = 1 if args and hasattr(args[0], func.__name__) else 0

            for i, expected_type in enumerate(param_types):
                arg_idx = start_idx + i
                if arg_idx < len(args):
                    actual_value = args[arg_idx]
                    if not isinstance(actual_value, expected_type):
                        raise TypeError(
                            f"{func.__name__} argument {i+1} must be {expected_type.__name__}, "
                            f"got {type(actual_value).__name__}"
                        )

            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_api_response_structure(*required_fields):
    """
    Decorator to validate that API response contains required fields.

    Args:
        *required_fields: Field names that must be present in the response dict
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            if result is None:
                logger.warning(f"{func.__name__} returned None - possible API failure")
                return result

            if isinstance(result, dict):
                missing_fields = [field for field in required_fields if field not in result]
                if missing_fields:
                    logger.error(f"{func.__name__} response missing required fields: {missing_fields}")
                    raise ESIRequestError(f"API response missing required fields: {missing_fields}")

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            if result is None:
                logger.warning(f"{func.__name__} returned None - possible API failure")
                return result

            if isinstance(result, dict):
                missing_fields = [field for field in required_fields if field not in result]
                if missing_fields:
                    logger.error(f"{func.__name__} response missing required fields: {missing_fields}")
                    raise ESIRequestError(f"API response missing required fields: {missing_fields}")

            return result

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def validate_numeric_bounds(min_value=None, max_value=None):
    """
    Decorator to validate that numeric parameters are within specified bounds.

    Args:
        min_value: Minimum allowed value (inclusive), None for no minimum
        max_value: Maximum allowed value (inclusive), None for no maximum
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Skip 'self' or 'cls' for methods/classmethods
            start_idx = 1 if args and hasattr(args[0], func.__name__) else 0

            for i, arg in enumerate(args[start_idx:], start_idx):
                if isinstance(arg, (int, float)):
                    if min_value is not None and arg < min_value:
                        raise ValueError(f"{func.__name__} argument {i} must be >= {min_value}, got {arg}")
                    if max_value is not None and arg > max_value:
                        raise ValueError(f"{func.__name__} argument {i} must be <= {max_value}, got {arg}")

            return func(*args, **kwargs)

        return wrapper

    return decorator


# Circuit Breaker implementation for better error handling
class CircuitBreakerState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Number of failures before opening
    recovery_timeout: int = 60  # Seconds to wait before trying half-open
    success_threshold: int = 3  # Number of successes needed to close circuit
    timeout: float = 30.0  # Request timeout in seconds


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
        elif self.state == CircuitBreakerState.CLOSED and self.failure_count >= self.config.failure_threshold:
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
_esi_circuit_breaker = CircuitBreaker(
    "ESI_API", CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60, success_threshold=3, timeout=30.0)
)

_wp_circuit_breaker = CircuitBreaker(
    "WordPress_API", CircuitBreakerConfig(failure_threshold=20, recovery_timeout=300, success_threshold=3, timeout=30.0)
)


class RateLimiter:
    """Rate limiter to prevent API abuse with configurable calls per minute."""

    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.calls = []

    async def wait_if_needed(self):
        """Wait if necessary to respect rate limits."""
        now = datetime.now()
        # Remove calls older than 1 minute
        self.calls = [call for call in self.calls if call > now - timedelta(minutes=1)]

        if len(self.calls) >= self.calls_per_minute:
            # Wait until the oldest call is more than 1 minute old
            wait_time = (self.calls[0] + timedelta(minutes=1) - now).total_seconds()
            if wait_time > 0:
                logger.info(
                    f"Rate limiter: Waiting {wait_time:.2f} seconds to respect "
                    f"{self.calls_per_minute} calls/minute limit"
                )
                await asyncio.sleep(wait_time)
                # Recheck after waiting
                return await self.wait_if_needed()

        self.calls.append(now)


# Global rate limiter for WordPress API
wp_rate_limiter = RateLimiter(calls_per_minute=60)  # 60 calls per minute default

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

    esi_base_url: str = "https://esi.evetech.net/latest"
    esi_timeout: int = 30
    esi_max_retries: int = 3
    esi_max_workers: int = 10
    wp_per_page: int = 100
    rate_limit_buffer: int = 1

    @classmethod
    def from_env(cls) -> "ApiConfig":
        """Create ApiConfig instance from environment variables."""
        return cls(
            esi_base_url=os.getenv("ESI_BASE_URL", "https://esi.evetech.net/latest"),
            esi_timeout=int(os.getenv("ESI_TIMEOUT", 30)),
            esi_max_retries=int(os.getenv("ESI_MAX_RETRIES", 3)),
            esi_max_workers=int(os.getenv("ESI_MAX_WORKERS", 10)),
            wp_per_page=int(os.getenv("WP_PER_PAGE", 100)),
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
            connector=aiohttp.TCPConnector(limit=api_config.esi_max_workers * 2),
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
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Set up structured JSON logging for performance monitoring
performance_logger = logging.getLogger("performance")
performance_logger.setLevel(logging.INFO)
perf_handler = logging.FileHandler("performance.log")
perf_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
performance_logger.addHandler(perf_handler)

# Set up audit logging for sensitive operations
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
audit_handler = logging.FileHandler("audit.log")
audit_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
audit_logger.addHandler(audit_handler)

# Prometheus-style metrics for API monitoring
try:
    from prometheus_client import Counter, Histogram

    ESI_REQUESTS_TOTAL = Counter("eve_esi_requests_total", "Total ESI API requests", ["endpoint_type", "status"])
    ESI_REQUEST_DURATION = Histogram("eve_esi_request_duration_seconds", "ESI API request duration", ["endpoint_type"])
    WP_REQUESTS_TOTAL = Counter("eve_wp_requests_total", "Total WordPress API requests", ["method", "status"])
    WP_REQUEST_DURATION = Histogram("eve_wp_request_duration_seconds", "WordPress API request duration", ["method"])

    API_METRICS_ENABLED = True
except ImportError:
    API_METRICS_ENABLED = False
    ESI_REQUESTS_TOTAL = ESI_REQUEST_DURATION = WP_REQUESTS_TOTAL = WP_REQUEST_DURATION = None


def log_audit_event(event: str, user: str, details: Dict[str, Any]) -> None:
    """Log audit events for security monitoring."""
    audit_logger.info(f"EVENT: {event} | USER: {user} | DETAILS: {details}")


def format_error_message(operation: str, resource_id: Any, error: Exception, context: Dict = None) -> str:
    """Format error messages consistently across the application.

    Args:
        operation: The operation that failed (e.g., 'fetch_character_data')
        resource_id: The resource identifier (e.g., character ID, endpoint)
        error: The exception that occurred
        context: Optional additional context information

    Returns:
        Formatted error message string
    """
    base_msg = f"{operation} failed for {resource_id}: {str(error)}"
    if context:
        context_str = ", ".join(f"{k}={v}" for k, v in context.items())
        return f"{base_msg} ({context_str})"
    return base_msg


@benchmark
async def _fetch_esi_with_retry(
    endpoint: str, headers: Optional[Dict[str, str]] = None, max_retries: int = None, is_public: bool = True
) -> Dict[str, Any]:
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
                        result = sanitize_api_response(result)  # Sanitize API response
                        elapsed = time.time() - start_time
                        endpoint_type = "public" if is_public else "authenticated"
                        logger.info(f"ESI {endpoint_type} fetch successful: {endpoint} in {elapsed:.2f}s")
                        if API_METRICS_ENABLED:
                            ESI_REQUESTS_TOTAL.labels(endpoint_type=endpoint_type, status="success").inc()
                            ESI_REQUEST_DURATION.labels(endpoint_type=endpoint_type).observe(elapsed)
                        return result
                    elif response.status == 401 and not is_public:
                        elapsed = time.time() - start_time
                        logger.error(f"Authentication failed for endpoint {endpoint} in {elapsed:.2f}s")
                        if API_METRICS_ENABLED:
                            ESI_REQUESTS_TOTAL.labels(endpoint_type="authenticated", status="auth_error").inc()
                        raise ESIAuthError(f"Authentication failed: {endpoint}")
                    elif response.status == 403 and not is_public:
                        elapsed = time.time() - start_time
                        logger.error(f"Access forbidden for endpoint {endpoint} in {elapsed:.2f}s")
                        if API_METRICS_ENABLED:
                            ESI_REQUESTS_TOTAL.labels(endpoint_type="authenticated", status="forbidden").inc()
                        raise ESIRequestError(f"Access forbidden: {endpoint}")
                    elif response.status == 404:
                        elapsed = time.time() - start_time
                        endpoint_type = "public" if is_public else ""
                        logger.warning(f"Resource not found for {endpoint_type} endpoint {endpoint} in {elapsed:.2f}s")
                        if API_METRICS_ENABLED:
                            ESI_REQUESTS_TOTAL.labels(
                                endpoint_type=endpoint_type or "unknown", status="not_found"
                            ).inc()
                        raise ESIRequestError(f"Resource not found: {endpoint}")
                    elif response.status == 429:  # Rate limited
                        # Check for X-ESI-Error-Limit-Remain header
                        error_limit_reset = response.headers.get("X-ESI-Error-Limit-Reset")

                        if error_limit_reset:
                            wait_time = int(error_limit_reset) + 1  # Add 1 second buffer
                            endpoint_type = "public" if is_public else ""
                            logger.info(f"RATE LIMIT: Waiting {wait_time} seconds for {endpoint_type} endpoint...")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            # Fallback: wait 60 seconds if no reset header
                            endpoint_type = "public" if is_public else ""
                            logger.info(
                                f"RATE LIMIT: Waiting 60 seconds for {endpoint_type} endpoint (no reset header)..."
                            )
                            await asyncio.sleep(60)
                            continue
                    elif response.status == 420:  # Error limited
                        error_limit_reset = response.headers.get("X-ESI-Error-Limit-Reset")

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
                            wait_time = 2**attempt  # Exponential backoff
                            logger.warning(f"SERVER ERROR {response.status}: Retrying in {wait_time} seconds...")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"SERVER ERROR {response.status}: Max retries exceeded")
                            raise ESIRequestError(f"Server error after {max_retries} retries: {endpoint}")
                    else:
                        elapsed = time.time() - start_time
                        logger.error(
                            f"ESI API error for {endpoint}: {response.status} - "
                            f"{await response.text()} (took {elapsed:.2f}s)"
                        )
                        raise ESIRequestError(f"ESI API error {response.status}: {endpoint}")

            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(f"TIMEOUT: Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    elapsed = time.time() - start_time
                    logger.error(f"TIMEOUT: Max retries exceeded for {endpoint} (took {elapsed:.2f}s)")
                    raise ESIRequestError(f"Timeout after {max_retries} retries: {endpoint}")
            except aiohttp.ClientError as e:
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
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


@validate_api_response
async def fetch_public_esi(endpoint: str, max_retries: int = None) -> Optional[Dict[str, Any]]:
    """
    Fetch data from ESI API (public endpoints, no auth) with rate limiting and error handling.

    This function handles public EVE Online ESI API endpoints that don't require authentication.
    It includes automatic retry logic, rate limiting, and circuit breaker protection.

    Args:
        endpoint: ESI API endpoint path (e.g., '/universe/types/123')
        max_retries: Maximum number of retry attempts (default: from config)

    Returns:
        Dictionary containing the API response data, or None if request failed

    Raises:
        ESIRequestError: If the API request fails after all retries

    Example:
        >>> data = await fetch_public_esi('/universe/types/123')
        >>> print(data['name'])  # 'Rifter'
        >>>
        >>> # Fetch multiple types concurrently
        >>> import asyncio
        >>> async def get_types(type_ids):
        ...     tasks = [fetch_public_esi(f'/universe/types/{tid}') for tid in type_ids]
        ...     return await asyncio.gather(*tasks)
        >>> types = asyncio.run(get_types([123, 456, 789]))
    """
    return await _fetch_esi_with_retry(endpoint, headers=None, max_retries=max_retries, is_public=True)


@validate_api_response
async def fetch_esi(
    endpoint: str, char_id: Optional[int], access_token: str, max_retries: int = None
) -> Optional[Dict[str, Any]]:
    """
    Fetch data from ESI API with authentication, rate limiting and error handling.

    This function handles authenticated EVE Online ESI API endpoints that require OAuth tokens.
    It includes automatic token validation, retry logic, rate limiting, and circuit breaker protection.

    Args:
        endpoint: ESI API endpoint path (e.g., '/characters/123/assets')
        char_id: Character ID for authentication context (can be None for some endpoints)
        access_token: Valid OAuth2 access token
        max_retries: Maximum number of retry attempts (default: from config)

    Returns:
        Dictionary containing the API response data, or None if request failed

    Raises:
        ESIAuthError: If authentication fails
        ESIRequestError: If the API request fails after all retries

    Example:
        >>> assets = await fetch_esi('/characters/123/assets', 123, 'token')
        >>> print(len(assets))  # Number of assets
        150
        >>>
        >>> # Fetch character skills
        >>> skills = await fetch_esi('/characters/123/skills', 123, 'token')
        >>> print(skills['total_sp'])  # Total skill points
        12345678
        >>>
        >>> # Fetch corporation data (char_id can be None for corp endpoints)
        >>> corp = await fetch_esi('/corporations/456', None, 'token')
        >>> print(corp['name'])  # Corporation name
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    return await _fetch_esi_with_retry(endpoint, headers=headers, max_retries=max_retries, is_public=False)


@validate_input_params(str, type(None), str)
def fetch_esi_sync(
    endpoint: str, char_id: Optional[int], access_token: str, max_retries: int = None
) -> Optional[Dict[str, Any]]:
    """Synchronous version of fetch_esi for compatibility with existing scripts."""
    return asyncio.run(fetch_esi(endpoint, char_id, access_token, max_retries))


@validate_input_params(str)
def fetch_public_esi_sync(endpoint: str, max_retries: int = None) -> Optional[Dict[str, Any]]:
    """Synchronous version of fetch_public_esi for compatibility with existing scripts."""
    return asyncio.run(fetch_public_esi(endpoint, max_retries))


@validate_input_params(int, int)
def fetch_public_contracts(region_id: int, page: int = 1, max_retries: int = 3) -> Optional[List[Dict[str, Any]]]:
    """Fetch public contracts for a specific region with retry logic and rate limiting.

    This function retrieves public contracts from the EVE ESI API for a given region,
    implementing exponential backoff retry logic and monitoring ESI rate limits.

    Args:
        region_id: The EVE region ID to fetch contracts from
        page: Page number for pagination (default: 1)
        max_retries: Maximum number of retry attempts on failure (default: 3)

    Returns:
        List of contract dictionaries if successful, None if all retries failed

    Note:
        ESI returns a maximum of 1000 contracts per page. Use pagination for complete results.
    """
    endpoint = f"/contracts/public/{region_id}/?page={page}"
    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {"Accept": "application/json"}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Check rate limiting
            remaining = response.headers.get("X-ESI-Error-Limit-Remain", "100")
            reset_time = response.headers.get("X-ESI-Error-Limit-Reset", "60")
            if int(remaining) < 20:
                logger.warning(f"ESI rate limit low: {remaining} requests remaining, resets in {reset_time}s")

            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # Exponential backoff
                logger.warning(
                    f"ESI request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s"
                )
                time.sleep(wait_time)
            else:
                logger.error(f"ESI request failed after {max_retries} attempts: {e}")
                return None


@validate_input_params(int, int)
def fetch_public_contract_items(contract_id: int, max_retries: int = 3) -> Optional[List[Dict[str, Any]]]:
    """Fetch items contained in a public contract with retry logic.

    Retrieves the list of items and their quantities for a specific public contract.
    Only works for contracts that are publicly visible (not private courier contracts).

    Args:
        contract_id: The EVE contract ID to fetch items for
        max_retries: Maximum number of retry attempts on failure (default: 3)

    Returns:
        List of contract item dictionaries if successful, None if failed

    Note:
        Item quantities are negative for blueprint originals (BPOs) and positive for copies (BPCs).
    """
    endpoint = f"/contracts/public/items/{contract_id}/"
    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {"Accept": "application/json"}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Check rate limiting
            remaining = response.headers.get("X-ESI-Error-Limit-Remain", "100")
            reset_time = response.headers.get("X-ESI-Error-Limit-Reset", "60")
            if int(remaining) < 20:
                logger.warning(f"ESI rate limit low: {remaining} requests remaining, resets in {reset_time}s")

            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # Exponential backoff
                logger.warning(
                    f"ESI request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s"
                )
                time.sleep(wait_time)
            else:
                logger.error(f"ESI request failed after {max_retries} attempts: {e}")
                return None


@validate_input_params(int, int)
async def fetch_public_contracts_async(
    region_id: int, page: int = 1, max_retries: int = 3
) -> Optional[List[Dict[str, Any]]]:
    """Fetch public contracts for a specific region asynchronously with retry logic and rate limiting.

    This function retrieves public contracts from the EVE ESI API for a given region,
    implementing exponential backoff retry logic and monitoring ESI rate limits.

    Args:
        region_id: The EVE region ID to fetch contracts from
        page: Page number for pagination (default: 1)
        max_retries: Maximum number of retry attempts on failure (default: 3)

    Returns:
        List of contract dictionaries if successful, None if all retries failed

    Note:
        ESI returns a maximum of 1000 contracts per page. Use pagination for complete results.
    """
    endpoint = f"/contracts/public/{region_id}/?page={page}"
    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {"Accept": "application/json"}

    sess = await get_session()
    for attempt in range(max_retries):
        try:
            async with sess.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()

                # Check rate limiting
                remaining = response.headers.get("X-ESI-Error-Limit-Remain", "100")
                reset_time = response.headers.get("X-ESI-Error-Limit-Reset", "60")
                if int(remaining) < 20:
                    logger.warning(f"ESI rate limit low: {remaining} requests remaining, resets in {reset_time}s")

                return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # Exponential backoff
                logger.warning(
                    f"ESI request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"ESI request failed after {max_retries} attempts: {e}")
                return None


@validate_input_params(int, int)
async def fetch_public_contract_items_async(contract_id: int, max_retries: int = 3) -> Optional[List[Dict[str, Any]]]:
    """Fetch items contained in a public contract asynchronously with retry logic.

    Retrieves the list of items and their quantities for a specific public contract.
    Only works for contracts that are publicly visible (not private courier contracts).

    Args:
        contract_id: The EVE contract ID to fetch items for
        max_retries: Maximum number of retry attempts on failure (default: 3)

    Returns:
        List of contract item dictionaries if successful, None if failed

    Note:
        Item quantities are negative for blueprint originals (BPOs) and positive for copies (BPCs).
    """
    endpoint = f"/contracts/public/items/{contract_id}/"
    url = f"{ESI_BASE_URL}{endpoint}"
    headers = {"Accept": "application/json"}

    sess = await get_session()
    for attempt in range(max_retries):
        try:
            async with sess.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()

                # Check rate limiting
                remaining = response.headers.get("X-ESI-Error-Limit-Remain", "100")
                reset_time = response.headers.get("X-ESI-Error-Limit-Reset", "60")
                if int(remaining) < 20:
                    logger.warning(f"ESI rate limit low: {remaining} requests remaining, resets in {reset_time}s")

                return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # Exponential backoff
                logger.warning(
                    f"ESI request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"ESI request failed after {max_retries} attempts: {e}")
                return None


@benchmark
async def wp_request(method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
    """
    Make authenticated request to WordPress REST API with circuit breaker protection.

    This function handles all WordPress REST API interactions with automatic authentication,
    rate limiting, retry logic, and circuit breaker protection.

    Args:
        method: HTTP method ('GET', 'POST', 'PUT', 'DELETE')
        endpoint: WordPress API endpoint path (e.g., '/wp-json/wp/v2/posts')
        data: Request payload for POST/PUT requests

    Returns:
        Dictionary containing the API response data, or None if request failed

    Raises:
        WordPressAuthError: If WordPress authentication fails
        WordPressRequestError: If the API request fails

    Example:
        >>> post = await wp_request('POST', '/wp-json/wp/v2/posts', {'title': 'New Post', 'status': 'publish'})
        >>> print(post['id'])  # 123
    """

    async def _do_wp_request():
        start_time = time.time()
        # Apply rate limiting
        await wp_rate_limiter.wait_if_needed()

        sess = await get_session()
        url = f"{WP_BASE_URL}{endpoint}"
        auth = aiohttp.BasicAuth(WP_USERNAME, WP_APP_PASSWORD)

        try:
            if method.upper() == "GET":
                async with sess.get(url, auth=auth) as response:
                    if response.status == 200:
                        result = await response.json()
                        result = sanitize_api_response(result)  # Sanitize API response
                        elapsed = time.time() - start_time
                        logger.info(f"WordPress GET successful: {endpoint} in {elapsed:.2f}s")
                        return result
                    elif response.status == 401:
                        elapsed = time.time() - start_time
                        logger.error(
                            f"WordPress authentication failed: {response.status} - "
                            f"{await response.text()} (took {elapsed:.2f}s)"
                        )
                        raise WordPressAuthError(f"Authentication failed for {endpoint}")
                    else:
                        elapsed = time.time() - start_time
                        logger.error(
                            f"WordPress API error: {response.status} - {await response.text()} (took {elapsed:.2f}s)"
                        )
                        raise WordPressRequestError(f"WordPress API error {response.status}: {endpoint}")
            elif method.upper() == "POST":
                async with sess.post(url, json=data, auth=auth) as response:
                    if response.status in [200, 201]:
                        result = await response.json()
                        result = sanitize_api_response(result)  # Sanitize API response
                        elapsed = time.time() - start_time
                        logger.info(f"WordPress POST successful: {endpoint} in {elapsed:.2f}s")
                        return result
                    elif response.status == 401:
                        elapsed = time.time() - start_time
                        logger.error(
                            f"WordPress authentication failed: {response.status} - "
                            f"{await response.text()} (took {elapsed:.2f}s)"
                        )
                        raise WordPressAuthError(f"Authentication failed for {endpoint}")
                    else:
                        elapsed = time.time() - start_time
                        logger.error(
                            f"WordPress API error: {response.status} - {await response.text()} (took {elapsed:.2f}s)"
                        )
                        raise WordPressRequestError(f"WordPress API error {response.status}: {endpoint}")
            elif method.upper() == "PUT":
                async with sess.put(url, json=data, auth=auth) as response:
                    if response.status in [200, 201]:
                        result = await response.json()
                        result = sanitize_api_response(result)  # Sanitize API response
                        elapsed = time.time() - start_time
                        logger.info(f"WordPress PUT successful: {endpoint} in {elapsed:.2f}s")
                        return result
                    elif response.status == 401:
                        elapsed = time.time() - start_time
                        logger.error(
                            f"WordPress authentication failed: {response.status} - "
                            f"{await response.text()} (took {elapsed:.2f}s)"
                        )
                        raise WordPressAuthError(f"Authentication failed for {endpoint}")
                    else:
                        elapsed = time.time() - start_time
                        logger.error(
                            f"WordPress API error: {response.status} - {await response.text()} (took {elapsed:.2f}s)"
                        )
                        raise WordPressRequestError(f"WordPress API error {response.status}: {endpoint}")
            elif method.upper() == "DELETE":
                params = {"force": "true"} if data and data.get("force") else None
                async with sess.delete(url, auth=auth, params=params) as response:
                    if response.status == 200:
                        elapsed = time.time() - start_time
                        logger.info(f"WordPress DELETE successful: {endpoint} in {elapsed:.2f}s")
                        return {"deleted": True}
                    elif response.status == 401:
                        elapsed = time.time() - start_time
                        logger.error(
                            f"WordPress authentication failed: {response.status} - "
                            f"{await response.text()} (took {elapsed:.2f}s)"
                        )
                        raise WordPressAuthError(f"Authentication failed for {endpoint}")
                    else:
                        elapsed = time.time() - start_time
                        logger.error(
                            f"WordPress API error: {response.status} - {await response.text()} (took {elapsed:.2f}s)"
                        )
                        raise WordPressRequestError(f"WordPress API error {response.status}: {endpoint}")
        except aiohttp.ClientError as e:
            elapsed = time.time() - start_time
            logger.error(f"WordPress API request failed: {e} (took {elapsed:.2f}s)")
            raise WordPressRequestError(f"Network error for WordPress API: {endpoint}")

        return None

    # Use circuit breaker to protect WordPress API calls
    return await _wp_circuit_breaker.call(_do_wp_request)


@validate_input_params(str, str)
def send_email(subject: str, body: str) -> None:
    """Send an email alert."""
    if not all([EMAIL_SMTP_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO]):
        logger.warning("Email configuration incomplete, skipping alert.")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    try:
        server = smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        server.quit()
        logger.info(f"Alert email sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")


@validate_input_params(str)
def refresh_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """
    Refresh an OAuth2 access token using a refresh token.

    Exchanges a valid refresh token for a new access token from EVE Online's OAuth server.
    Automatically calculates the token expiration time and logs audit events.

    Args:
        refresh_token: Valid OAuth2 refresh token

    Returns:
        Dictionary with token data:
        {
            'access_token': str,
            'refresh_token': str,  # May be the same or new
            'expires_at': str  # ISO format datetime
        }
        Returns None if refresh fails

    Raises:
        No explicit raises; logs errors internally

    Example:
        >>> tokens = refresh_token('refresh_token_123')
        >>> if tokens:
        ...     print(f"New token expires: {tokens['expires_at']}")
    """
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    client_id = os.getenv("ESI_CLIENT_ID")
    client_secret = os.getenv("ESI_CLIENT_SECRET")
    response = requests.post("https://login.eveonline.com/v2/oauth/token", data=data, auth=(client_id, client_secret))
    if response.status_code == 200:
        token_data = response.json()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
        result = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", refresh_token),
            "expires_at": expires_at.isoformat(),
        }
        # Audit log successful token refresh
        log_audit_event(
            "TOKEN_REFRESH_SUCCESS", "system", {"client_id": client_id[:8] + "..." if client_id else "unknown"}
        )
        return result
    else:
        # Audit log failed token refresh
        log_audit_event(
            "TOKEN_REFRESH_FAILURE",
            "system",
            {"status_code": response.status_code, "client_id": client_id[:8] + "..." if client_id else "unknown"},
        )
        logger.error(f"Failed to refresh token: {response.status_code} - {response.text}")
        return None


@validate_api_response
@validate_input_params(int)
async def fetch_type_icon(type_id: int, size: int = 512) -> str:
    """
    Fetch type icon URL from EVE Online image servers with fallback logic.

    Attempts to retrieve item type icons from images.evetech.net, trying multiple
    variations (regular icon, blueprint icon) and falling back to placeholder if needed.

    Args:
        type_id: EVE item type ID
        size: Icon size in pixels (default: 512)

    Returns:
        URL string pointing to the icon image

    Example:
        >>> icon_url = await fetch_type_icon(12345, size=256)
        >>> print(icon_url)  # 'https://images.evetech.net/types/12345/icon?size=256'
    """
    # Try the 'bp' variation first for blueprints, then fallback to regular icon
    variations = ["bp", "icon"]

    sess = await get_session()
    for variation in variations:
        icon_url = f"https://images.evetech.net/types/{type_id}/{variation}?size={size}"
        # Test if the URL exists by making a HEAD request
        try:
            async with sess.head(icon_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    return icon_url
        except Exception:
            continue

    # If no icon found, return placeholder
    return f"https://via.placeholder.com/{size}x{size}/cccccc/000000?text=No+Icon"


@validate_api_response
@validate_input_params(int)
async def fetch_planet_details(char_id: int, planet_id: int, access_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch detailed planetary colony information from ESI.

    Retrieves detailed information about a specific planetary colony,
    including resource extraction, factory setups, and colony status.

    Args:
        char_id: EVE character ID that owns the colony.
        planet_id: Specific planet ID to fetch details for.
        access_token: Valid OAuth2 access token for authentication.

    Returns:
        Optional[Dict[str, Any]]: Detailed planet colony data if successful.
    """
    endpoint = f"/characters/{char_id}/planets/{planet_id}/"
    return await fetch_esi(endpoint, char_id, access_token)


@validate_input_params((str, type(None)))
def sanitize_string(value: str) -> str:
    return re.sub(r"[^\w\s\-.,]", "", value) if isinstance(value, str) else str(value)


@validate_input_params()
def sanitize_api_response(data: Any) -> Any:
    """Sanitize API response data recursively to prevent injection and ensure type safety."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if isinstance(k, str) and re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", k):  # Valid key names only
                sanitized[k] = sanitize_api_response(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_api_response(item) for item in data]
    elif isinstance(data, str):
        # Basic sanitization: remove potentially dangerous characters
        return re.sub(r"[^\w\s\-.,@/:]", "", data)
    elif isinstance(data, (int, float, bool)) or data is None:
        # Allow primitive types as-is
        return data
    else:
        # Convert unknown types to string and sanitize
        return sanitize_string(str(data))


def delete_wp_post(post_type: str, post_id: int) -> bool:
    """
    Delete a WordPress post synchronously.

    Deletes a post from WordPress using the REST API. This is a synchronous
    wrapper around the async wp_request function.

    Args:
        post_type: WordPress post type (e.g., 'eve_blueprint', 'eve_contract')
        post_id: WordPress post ID to delete

    Returns:
        bool: True if deletion was successful, False otherwise

    Note:
        Uses asyncio.run() to execute the async wp_request in a synchronous context.
    """
    endpoint = f"/wp/v2/{post_type}/{post_id}"
    result = asyncio.run(wp_request("DELETE", endpoint, {"force": True}))
    return result is not None and result.get("deleted", False)
