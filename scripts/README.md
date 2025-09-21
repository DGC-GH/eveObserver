# EVE Observer Scripts

This directory contains Python scripts for interacting with the EVE ESI API and WordPress. The system provides comprehensive monitoring of EVE Online corporations and characters, including blueprints, industry jobs, contracts, planets, and market data.

## Features

- **Corporation Monitoring**: Track corporation blueprints, assets, contracts, and industry jobs
- **Character Monitoring**: Monitor character skills, blueprints, planets, and contracts
- **Industry Alerts**: Automatic email notifications for job completions and PI extractions
- **WordPress Integration**: Store all data in custom post types for easy access
- **Caching System**: Optimized performance with intelligent caching
- **Pagination Support**: Dashboard handles large datasets efficiently
- **Configurable**: Environment-based configuration for easy deployment

## Prerequisites

- Python 3.8+
- WordPress installation with REST API enabled
- EVE Online developer application
- Application Password for WordPress

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. EVE Developer Application

1. Go to https://developers.eveonline.com/
2. Create a new application
3. Set callback URL to: `http://localhost:8080/callback`
4. Select the following scopes:
   - `esi-characters.read_blueprints.v1`
   - `esi-characters.read_contacts.v1`
   - `esi-characters.read_corporations_roles.v1`
   - `esi-characters.read_industry_jobs.v1`
   - `esi-characters.read_assets.v1`
   - `esi-characters.read_contracts.v1`
   - `esi-characters.read_planets.v1`
   - `esi-characters.read_standings.v1`
   - `esi-corporations.read_blueprints.v1`
   - `esi-corporations.read_assets.v1`
   - `esi-corporations.read_contracts.v1`
   - `esi-corporations.read_industry_jobs.v1`
   - `esi-corporations.read_standings.v1`
   - `esi-markets.read_character_orders.v1`
   - `esi-markets.read_corporation_orders.v1`

### 3. WordPress Configuration

1. Install WordPress and enable REST API
2. Create an Application Password for your user
3. Install required plugins:
   - Custom Post Types (or use the provided PHP file)
4. Set up custom post types for:
   - `eve_character`
   - `eve_corporation`
   - `eve_blueprint`
   - `eve_planet`
   - `eve_contract`

### 4. Environment Configuration

Create a `.env` file in the scripts directory:

```env
# EVE ESI Configuration
ESI_CLIENT_ID=your_client_id_here
ESI_CLIENT_SECRET=your_client_secret_here
ESI_BASE_URL=https://esi.evetech.net
ESI_TIMEOUT=30
ESI_MAX_WORKERS=10

# WordPress Configuration
WP_BASE_URL=https://your-wordpress-site.com
WP_USERNAME=your_username
WP_APP_PASSWORD=your_application_password
WP_PER_PAGE=100

# Application Configuration
ALLOWED_CORPORATIONS=Corp1,Corp2,Corp3
LOG_LEVEL=INFO
LOG_FILE=logs/eve_observer.log

# Email Configuration (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=alerts@yourdomain.com
```

## Scripts Overview

### `esi_oauth.py` - OAuth Authentication

Handles EVE Online OAuth authentication for character access.

**Commands:**
```bash
# Authorize a single character
python esi_oauth.py authorize

# Authorize all characters in sequence
python esi_oauth.py authorize_all

# List authorized characters
python esi_oauth.py list

# Remove a character
python esi_oauth.py remove <character_id>
```

### `fetch_data.py` - Data Fetching

Main script that fetches data from ESI and stores it in WordPress.

**Usage:**
```bash
# Run data fetching
python fetch_data.py

# With debug logging
LOG_LEVEL=DEBUG python fetch_data.py
```

**What it does:**
- Refreshes expired tokens automatically
- Fetches corporation and character data
- Processes blueprints from multiple sources
- Updates WordPress with latest information
- Sends email alerts for industry completions

## Configuration

The system uses a centralized configuration system (`config.py`) that supports:

- Environment variables for sensitive data
- Default values for optional settings
- Validation of required configuration
- Type conversion and error handling

### Key Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `ESI_TIMEOUT` | API request timeout (seconds) | 30 |
| `ESI_MAX_WORKERS` | Parallel processing workers | 10 |
| `WP_PER_PAGE` | WordPress API page size | 100 |
| `ALLOWED_CORPORATIONS` | Comma-separated corp names | None |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |

## Dashboard Features

The JavaScript dashboard (`js/dashboard.js`) provides:

- **Real-time Charts**: Character, blueprint, and planet counts
- **Blueprint Management**: Paginated blueprint listings with ME/TE info
- **Planet Interaction**: PI colony monitoring with extraction timers
- **Pagination**: Handles large datasets efficiently (10 items per page)
- **Responsive Design**: Works on desktop and mobile devices

## Troubleshooting

### Common Issues

#### 1. Authentication Errors
```
Error: No authorized characters found
```
**Solution:** Run `python esi_oauth.py authorize` to authenticate characters.

#### 2. WordPress Connection Issues
```
HTTPError: 401 Unauthorized
```
**Solution:** Check WordPress Application Password and URL in `.env`.

#### 3. ESI Rate Limiting
```
HTTPError: 420 Error Limited
```
**Solution:** The script handles rate limiting automatically. Wait and retry.

#### 4. Missing Dependencies
```
ModuleNotFoundError: No module named 'requests'
```
**Solution:** Run `pip install -r requirements.txt`.

#### 5. Permission Errors
```
HTTPError: 403 Forbidden
```
**Solution:** Ensure character has appropriate corporation roles for corp data.

### Debug Mode

Enable detailed logging:
```bash
LOG_LEVEL=DEBUG python fetch_data.py
```

### Logs

Check the log file specified in `LOG_FILE` for detailed error information.

## Architecture

### Data Flow

1. **Authentication**: OAuth tokens stored in `esi_tokens.json`
2. **Data Fetching**: Parallel ESI API calls with caching
3. **Processing**: Data transformation and validation
4. **Storage**: WordPress REST API updates
5. **Alerts**: Email notifications for important events

### Caching System

- **Blueprint Cache**: `cache/blueprints.json`
- **Location Cache**: `cache/locations.json`
- **Structure Cache**: `cache/structures.json`
- **WordPress Post ID Cache**: `cache/wp_post_ids.json`

### Email Alerts

Automatic notifications for:
- Industry job completions (24h window)
- PI extraction endings (24h window)

Configure SMTP settings in `.env` to enable.

## Development

### Code Organization

The codebase is organized into focused functions:
- `collect_corporation_members()`: Token management and corp grouping
- `process_corporation_data()`: Corporation data processing
- `process_character_data()`: Individual character processing
- Helper functions for specific data types (blueprints, contracts, planets)

### Testing

Run the test suite with pytest:
```bash
pytest tests/
```

Run tests with coverage:
```bash
pytest tests/ --cov=.
```

Run specific test categories:
```bash
pytest tests/ -m unit        # Unit tests only
pytest tests/ -m integration # Integration tests only
```

### Test Structure

- `tests/test_config.py`: Configuration loading and validation tests
- `tests/test_fetch_data.py`: Core data fetching function tests
- `pytest.ini`: Test configuration and markers

### Contributing

1. Follow PEP 8 style guidelines
2. Add type hints for new functions
3. Update documentation for API changes
4. Test with multiple corporations/characters

## Security Notes

- Never commit `.env` files or tokens to version control
- Use read-only ESI scopes when possible
- Regularly rotate Application Passwords
- Monitor log files for unauthorized access attempts

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review log files for error details
3. Ensure all prerequisites are met
4. Test with a single character first