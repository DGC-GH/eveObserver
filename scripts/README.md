# EVE Observer Scripts

This directory contains Python scripts for interacting with the EVE ESI API and WordPress.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure `.env` file with your ESI app credentials and WordPress details.

3. Register an EVE app at https://developers.eveonline.com/ to get Client ID and Secret.

## Scripts

- `esi_oauth.py`: Handles OAuth authentication for EVE characters.
- `fetch_data.py`: Fetches data from ESI and stores in WordPress.

## Usage

1. Authorize characters:
   ```bash
   python esi_oauth.py authorize
   ```

2. Fetch data:
   ```bash
   python fetch_data.py
   ```

3. List authorized characters:
   ```bash
   python esi_oauth.py list
   ```

## Notes

- Tokens are stored in `esi_tokens.json`.
- Scripts use read-only ESI scopes for compliance.
- WordPress integration uses REST API with Application Passwords.