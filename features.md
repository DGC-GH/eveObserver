# EVE Observer: Comprehensive Data Aggregation & Content Management System

## Executive Summary

This document serves as a complete blueprint for replicating the success of the EVE Observer project. It contains all architectural patterns, best practices, testing strategies, performance optimizations, security measures, and development methodologies implemented in this production-ready codebase. Use this as your primary guide when refactoring POC versions in other repositories.

## 🏗️ Architecture & Design Patterns

### Modular Architecture with Single Responsibility Principle
- **Separation of Concerns**: Each module handles one domain (contracts, blueprints, characters, corporations)
- **Re-export Pattern**: Maintain backward compatibility while evolving internal structure
- **Dependency Injection**: Clean interfaces between components
- **Configuration-Driven**: Environment-based configuration with validation

**Implementation Pattern:**
```python
# config.py - Centralized configuration
from typing import Optional
import os

class Config:
    def __init__(self):
        self.esi_timeout = int(os.getenv("ESI_TIMEOUT", 30))
        self.max_workers = int(os.getenv("MAX_WORKERS", 10))
        # ... validation and defaults

# api_client.py - Focused API interactions
class APIClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = None

    async def fetch_data(self, endpoint: str) -> dict:
        # Implementation
```

### Asynchronous-First Design
- **Async/Await Everywhere**: All I/O operations are non-blocking
- **Connection Pooling**: Reuse HTTP connections with aiohttp.ClientSession
- **Concurrent Processing**: Semaphores and gather() for controlled parallelism
- **Timeout Management**: Comprehensive timeout handling for all requests

**Key Patterns:**
```python
# Session management
async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=20)
        )
    return _session

# Concurrent processing with limits
async def process_batch(items: List[dict], concurrency: int = 5) -> List[dict]:
    semaphore = asyncio.Semaphore(concurrency)
    async def process_item(item):
        async with semaphore:
            return await process_single(item)
    return await asyncio.gather(*[process_item(item) for item in items])
```

## 🔧 Development Workflow & Code Quality

### Automated Code Quality Pipeline
**Tools Configuration:**
```toml
# pyproject.toml
[tool.black]
line-length = 88  # Or 120 based on preference
target-version = ['py39']

[tool.isort]
profile = "black"
line_length = 88

[tool.flake8]
max-line-length = 88
extend-ignore = ["E203"]  # Allow whitespace before : in slices

[tool.bandit]
exclude_dirs = ["tests"]
skips = ["B101", "B601"]  # Customize based on needs
```

**Pre-commit Hooks:**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files

  - repo: https://github.com/psf/black
    rev: 23.9.0
    hooks:
      - id: black
        language_version: python3.9

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
```

### Import Organization Strategy
```python
# 1. Standard library imports
import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

# 2. Third-party imports (alphabetical)
import aiohttp
import requests
from dotenv import load_dotenv

# 3. Local imports (alphabetical, with blank line separation)
from config import ESI_BASE_URL, ESI_TIMEOUT
from api_client import get_session
```

### Type Hints & Documentation
```python
from typing import Any, Dict, List, Optional, Union

def process_data(items: List[Dict[str, Any]]) -> Dict[str, List[dict]]:
    """
    Process a list of data items.

    Args:
        items: List of dictionaries containing item data

    Returns:
        Dictionary with processed results

    Raises:
        ValueError: If items is empty
        APIError: If external API calls fail
    """
    if not items:
        raise ValueError("Items list cannot be empty")

    # Implementation with proper error handling
    try:
        return {"processed": items, "count": len(items)}
    except Exception as e:
        logger.error(f"Failed to process items: {e}")
        raise APIError(f"Processing failed: {e}") from e
```

## 🧪 Comprehensive Testing Strategy

### Test Structure & Organization
```
tests/
├── __init__.py
├── conftest.py          # Shared fixtures and configuration
├── test_config.py       # Configuration validation tests
├── test_api_client.py   # API interaction tests
├── test_cache_manager.py # Caching logic tests
├── test_integration.py  # End-to-end integration tests
└── test_processors/     # Domain-specific processor tests
    ├── test_contract_processor.py
    ├── test_character_processor.py
    └── test_corporation_processor.py
```

### Testing Configuration
```python
# conftest.py
import pytest
import warnings

def pytest_configure(config):
    """Configure pytest markers and warnings."""
    config.addinivalue_line("markers", "unit: Fast unit tests")
    config.addinivalue_line("markers", "integration: Slower integration tests")
    config.addinivalue_line("markers", "slow: Very slow tests")

    # Suppress known warnings
    warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

# pytest.ini
[tool:pytest]
testpaths = tests
addopts =
    --verbose
    --tb=short
    --strict-markers
    --cov=scripts
    --cov-report=html
    --cov-report=term-missing
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
```

### Async Testing Patterns
```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_api_fetch_success():
    """Test successful API fetch."""
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.json.return_value = {"data": "test"}
    mock_session.get.return_value.__aenter__.return_value = mock_response

    with patch('api_client.get_session', return_value=mock_session):
        result = await fetch_data("test_endpoint")
        assert result == {"data": "test"}

@pytest.mark.asyncio
async def test_api_fetch_timeout():
    """Test API timeout handling."""
    mock_session = AsyncMock()
    mock_session.get.side_effect = asyncio.TimeoutError()

    with patch('api_client.get_session', return_value=mock_session):
        with pytest.raises(APIError, match="Request timeout"):
            await fetch_data("test_endpoint")
```

### Mocking Strategy
```python
# Use pytest-mock for comprehensive mocking
def test_processor_with_mocking(mocker):
    """Test processor with mocked dependencies."""
    # Mock external API calls
    mock_api = mocker.patch('api_client.fetch_data')
    mock_api.return_value = {"status": "success"}

    # Mock cache operations
    mock_cache = mocker.patch('cache_manager.load_cache')
    mock_cache.return_value = {}

    # Test the processor
    result = process_data()
    assert result["status"] == "processed"
```

## 🚀 Performance Optimization Techniques

### Multi-Level Caching Architecture
```python
class CacheManager:
    def __init__(self):
        self.memory_cache = LRUCache(max_size=1000)
        self.disk_cache = {}  # Persistent storage
        self.compression_enabled = True

    async def get(self, key: str) -> Optional[Any]:
        """Get with multi-level lookup."""
        # 1. Check memory cache
        value = self.memory_cache.get(key)
        if value is not None:
            self._record_hit("memory")
            return value

        # 2. Check disk cache
        value = await self._load_from_disk(key)
        if value is not None:
            self.memory_cache.put(key, value)  # Promote to memory
            self._record_hit("disk")
            return value

        self._record_miss()
        return None

    async def put(self, key: str, value: Any, ttl: int = 3600):
        """Put with compression and TTL."""
        compressed_value = self._compress(value) if self.compression_enabled else value

        cache_entry = {
            "value": compressed_value,
            "timestamp": time.time(),
            "ttl": ttl
        }

        # Update both caches
        self.memory_cache.put(key, cache_entry)
        await self._save_to_disk(key, cache_entry)
```

### Connection Pooling & Session Management
```python
# Global session with proper lifecycle management
_session: Optional[aiohttp.ClientSession] = None
_session_lock = asyncio.Lock()

async def get_session() -> aiohttp.ClientSession:
    """Get or create shared session."""
    global _session
    async with _session_lock:
        if _session is None or _session.closed:
            _session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30, sock_read=10),
                connector=aiohttp.TCPConnector(
                    limit=20,  # Connection pool size
                    ttl_dns_cache=300,  # DNS cache TTL
                    use_dns_cache=True
                ),
                headers={
                    "User-Agent": "EVE-Observer/1.0",
                    "Accept": "application/json"
                }
            )
    return _session

async def cleanup_session():
    """Properly close session on shutdown."""
    global _session
    if _session and not _session.closed:
        await _session.close()
```

### Batch Processing & Rate Limiting
```python
class RateLimiter:
    def __init__(self, calls_per_second: float = 10.0):
        self.calls_per_second = calls_per_second
        self.last_call = 0.0
        self.lock = asyncio.Lock()

    async def wait_if_needed(self):
        """Wait if necessary to respect rate limits."""
        async with self.lock:
            now = time.time()
            time_since_last = now - self.last_call
            min_interval = 1.0 / self.calls_per_second

            if time_since_last < min_interval:
                wait_time = min_interval - time_since_last
                await asyncio.sleep(wait_time)

            self.last_call = time.time()

async def process_batch_with_rate_limit(items: List[dict], rate_limiter: RateLimiter):
    """Process items with rate limiting."""
    results = []
    for item in items:
        await rate_limiter.wait_if_needed()
        result = await process_item(item)
        results.append(result)
    return results
```

### Benchmarking & Performance Monitoring
```python
import time
import functools
from typing import Callable, Any

def benchmark(func: Callable) -> Callable:
    """Decorator to measure function execution time."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            elapsed = time.perf_counter() - start
            logger.info(f"{func.__name__} completed in {elapsed:.3f}s")

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            elapsed = time.perf_counter() - start
            logger.info(f"{func.__name__} completed in {elapsed:.3f}s")

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

# Usage
@benchmark
async def fetch_large_dataset():
    # Implementation
    pass
```

## 🔒 Security & Resilience Patterns

### Input Validation & Sanitization
```python
import re
from typing import Union

def sanitize_string(input_str: Union[str, None]) -> str:
    """Sanitize string input to prevent injection attacks."""
    if input_str is None:
        return ""

    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>]', '', str(input_str))

    # Limit length
    return sanitized[:1000]  # Reasonable limit

def validate_api_response(response_data: dict) -> bool:
    """Validate API response structure."""
    required_fields = ['id', 'name']
    if not isinstance(response_data, dict):
        return False

    return all(field in response_data for field in required_fields)
```

### Circuit Breaker Pattern
```python
from enum import Enum
import time

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = CircuitState.CLOSED

    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerError("Circuit is open")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        """Reset circuit on success."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def _on_failure(self):
        """Handle failure and potentially open circuit."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
```

### Secure Configuration Management
```python
# config.py
import os
import secrets
from typing import Optional

class Config:
    def __init__(self):
        # API Keys - never log these
        self.api_key = os.getenv("API_KEY")
        self.database_url = os.getenv("DATABASE_URL")

        # Validate required config
        self._validate_config()

    def _validate_config(self):
        """Validate configuration on startup."""
        required = ['API_KEY', 'DATABASE_URL']
        missing = [key for key in required if not os.getenv(key)]

        if missing:
            raise ValueError(f"Missing required environment variables: {missing}")

    def get_connection_string(self) -> str:
        """Get sanitized connection string for logging."""
        # Mask sensitive parts
        url = self.database_url
        if 'password' in url:
            # Replace password in logs
            return re.sub(r'password=[^&]+', 'password=***', url)
        return url
```

### Audit Logging
```python
import logging
from datetime import datetime
from typing import Dict, Any

audit_logger = logging.getLogger('audit')

def log_audit_event(event_type: str, user_id: Optional[str] = None,
                   details: Optional[Dict[str, Any]] = None):
    """Log security-relevant events."""
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "user_id": user_id,
        "details": details or {},
        "ip_address": get_client_ip(),  # If applicable
    }

    audit_logger.info(f"AUDIT: {json.dumps(event)}")

# Usage
async def authenticate_user(token: str):
    try:
        user = await validate_token(token)
        log_audit_event("authentication_success", user.id)
        return user
    except Exception as e:
        log_audit_event("authentication_failure", details={"error": str(e)})
        raise
```

## 📊 Monitoring & Observability

### Prometheus Metrics Integration
```python
try:
    from prometheus_client import Counter, Histogram, Gauge

    # API Metrics
    API_REQUESTS_TOTAL = Counter(
        "api_requests_total",
        "Total API requests",
        ["endpoint", "method", "status"]
    )
    API_REQUEST_DURATION = Histogram(
        "api_request_duration_seconds",
        "API request duration",
        ["endpoint"]
    )

    # Cache Metrics
    CACHE_HITS = Counter("cache_hits_total", "Cache hits", ["cache_type"])
    CACHE_MISSES = Counter("cache_misses_total", "Cache misses", ["cache_type"])
    CACHE_SIZE = Gauge("cache_size", "Current cache size", ["cache_type"])

    METRICS_ENABLED = True
except ImportError:
    METRICS_ENABLED = False

def record_api_call(endpoint: str, method: str, status: int, duration: float):
    """Record API call metrics."""
    if METRICS_ENABLED:
        API_REQUESTS_TOTAL.labels(endpoint, method, status).inc()
        API_REQUEST_DURATION.labels(endpoint).observe(duration)
```

### Structured Logging
```python
import logging
import json
from pythonjsonlogger import jsonlogger

def setup_logging():
    """Configure structured JSON logging."""
    logger = logging.getLogger()

    # JSON formatter for production
    json_formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler with JSON
    file_handler = logging.FileHandler('app.log')
    file_handler.setFormatter(json_formatter)

    # Console handler with human-readable format
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)

# Usage
logger.info("Processing started", extra={
    "user_id": "123",
    "operation": "data_sync",
    "items_count": 150
})
```

### Health Checks & System Monitoring
```python
from typing import Dict, Any
import psutil
import asyncio

async def health_check() -> Dict[str, Any]:
    """Comprehensive health check endpoint."""
    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Database connectivity
    try:
        await db.ping()
        health["checks"]["database"] = "ok"
    except Exception as e:
        health["checks"]["database"] = f"error: {e}"
        health["status"] = "unhealthy"

    # External API connectivity
    try:
        await test_api_connectivity()
        health["checks"]["api"] = "ok"
    except Exception as e:
        health["checks"]["api"] = f"error: {e}"
        health["status"] = "degraded"

    # System resources
    health["checks"]["memory"] = {
        "used_mb": psutil.virtual_memory().used / 1024 / 1024,
        "available_mb": psutil.virtual_memory().available / 1024 / 1024,
        "percentage": psutil.virtual_memory().percent
    }

    # Cache status
    health["checks"]["cache"] = {
        "size": cache_manager.size(),
        "hit_rate": cache_manager.hit_rate()
    }

    return health
```

## 🐳 Deployment & DevOps

### Docker Configuration
```dockerfile
# Dockerfile
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run application
CMD ["python", "main.py"]
```

### Environment-Based Configuration
```bash
# .env.example
# API Configuration
ESI_BASE_URL=https://esi.evetech.net/latest
ESI_TIMEOUT=30
ESI_MAX_RETRIES=3

# Database
DATABASE_URL=postgresql://user:password@localhost/dbname

# External Services
REDIS_URL=redis://localhost:6379
WORDPRESS_URL=https://your-site.com/wp-json/wp/v2

# Security
SECRET_KEY=your-secret-key-here
API_KEY=your-api-key

# Logging
LOG_LEVEL=INFO
LOG_FILE=app.log

# Performance Tuning
MAX_WORKERS=10
CACHE_SIZE=1000
BATCH_SIZE=100
```

### CI/CD Pipeline
```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run tests
        run: |
          pytest --cov=scripts --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install linting tools
        run: |
          pip install black isort flake8 bandit

      - name: Run linters
        run: |
          black --check .
          isort --check-only .
          flake8 .
          bandit -r scripts/
```

## 📚 Implementation Guide

### Starting a New Project
1. **Set up project structure:**
   ```
   project/
   ├── scripts/
   │   ├── __init__.py
   │   ├── config.py
   │   ├── api_client.py
   │   ├── cache_manager.py
   │   └── main.py
   ├── tests/
   │   ├── __init__.py
   │   ├── conftest.py
   │   └── test_*.py
   ├── requirements.txt
   ├── pyproject.toml
   ├── pytest.ini
   └── .env.example
   ```

2. **Implement core components in order:**
   - Configuration management
   - Logging setup
   - API client with async patterns
   - Caching layer
   - Domain processors
   - Testing framework

3. **Apply quality standards:**
   - Set up pre-commit hooks
   - Configure code formatting
   - Implement comprehensive testing
   - Add monitoring and metrics

### Refactoring POC to Production
1. **Identify bottlenecks:** Profile current code for performance issues
2. **Implement async patterns:** Convert blocking operations to async
3. **Add comprehensive caching:** Multi-level caching for all external calls
4. **Implement proper error handling:** Circuit breakers, retries, graceful degradation
5. **Add monitoring:** Metrics, logging, health checks
6. **Security hardening:** Input validation, secure config, audit logging
7. **Testing:** Unit tests, integration tests, performance tests
8. **Code quality:** Formatting, linting, type hints, documentation

### Performance Tuning Checklist
- [ ] Profile application with real data loads
- [ ] Implement connection pooling for external APIs
- [ ] Add intelligent caching with TTL
- [ ] Use batch processing for bulk operations
- [ ] Implement rate limiting and backoff strategies
- [ ] Add compression for cache storage
- [ ] Use async/await for all I/O operations
- [ ] Implement circuit breakers for resilience
- [ ] Add performance monitoring and alerting
- [ ] Optimize data structures and algorithms

### Security Audit Checklist
- [ ] Input validation on all user inputs
- [ ] Secure credential storage (environment variables)
- [ ] HTTPS-only for all external communications
- [ ] Rate limiting to prevent abuse
- [ ] Audit logging for sensitive operations
- [ ] Sanitization of data before processing
- [ ] Timeout handling to prevent hanging requests
- [ ] Secure error messages (no sensitive data leakage)
- [ ] Dependency vulnerability scanning
- [ ] Regular security updates

## 🎯 Success Metrics

### Code Quality Metrics
- **Test Coverage:** >90% with pytest-cov
- **Code Quality:** Zero flake8 violations
- **Type Coverage:** 100% type hints on public APIs
- **Documentation:** Complete docstrings for all public functions

### Performance Metrics
- **Response Time:** <500ms for cached requests, <2s for API calls
- **Throughput:** Handle 100+ concurrent requests
- **Cache Hit Rate:** >80% for frequently accessed data
- **Memory Usage:** <500MB under normal load

### Reliability Metrics
- **Uptime:** 99.9% availability
- **Error Rate:** <0.1% of requests
- **Recovery Time:** <30 seconds from failures
- **Data Consistency:** 100% accuracy in processed data

### Development Velocity
- **Build Time:** <5 minutes for full CI pipeline
- **Test Execution:** <2 minutes for unit tests
- **Deployment Frequency:** Multiple times per day
- **Time to Resolution:** <1 hour for critical bugs

## 📖 Lessons Learned

### Technical Lessons
1. **Async is not optional** - Modern Python applications must be async-first
2. **Caching is critical** - Implement multi-level caching from day one
3. **Testing saves time** - Comprehensive testing prevents regressions
4. **Monitoring enables reliability** - Observable systems are maintainable systems
5. **Security is everyone's responsibility** - Build security into every component

### Process Lessons
1. **Start with quality standards** - Code formatting and linting from the beginning
2. **Automate everything** - CI/CD, testing, deployment should be automated
3. **Measure performance** - Benchmarking and monitoring prevent performance degradation
4. **Fail fast, recover quickly** - Circuit breakers and graceful degradation improve resilience
5. **Document decisions** - Architecture decisions should be documented for future maintainers

### Team Lessons
1. **Code reviews are essential** - Peer review catches issues and shares knowledge
2. **Pair programming accelerates learning** - Collaborative development improves quality
3. **Continuous integration prevents integration hell** - Regular merging prevents conflicts
4. **Knowledge sharing is key** - Document patterns and best practices
5. **Celebrate successes** - Recognize achievements to maintain motivation

Use this comprehensive guide to transform your POC into a production-ready system that matches the quality, performance, and reliability standards established in the EVE Observer project. The patterns and practices documented here have been proven to work at scale and will serve as a solid foundation for any data aggregation and content management system.
