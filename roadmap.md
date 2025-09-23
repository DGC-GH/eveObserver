# EVE Observer Roadmap

This roadmap outlines the prioritized improvements for the EVE Observer project, based on code analysis and user feedback. Tasks are ordered for optimal execution, starting with critical bug fixes and progressing to enhancements.

## Phase 1: Bug Fixes and Debugging (High Priority)

### ✅ Debug competing contracts detection - COMPLETED

- Isolated contract comparison logic inconsistencies between fetch_data.py and check_contract_outbid.py
- Fixed same-issuer contract exclusion bug in check_contract_outbid.py
- Standardized field names (_eve_contract_competing_price) and boolean values ('1'/'0')
- Added proper contract_issuer_id filtering to prevent false outbid detections

### ✅ Fix competing contracts logic - COMPLETED

- Updated contract processing functions to exclude same-issuer contracts
- Standardized outbid status fields between main script and standalone checker
- Fixed boolean value inconsistencies ('true'/'false' vs '1'/'0')

### Clean up temporary debug files and logs

- Remove debug scripts and excessive logging
- Consolidate logs to reduce clutter
- Commit cleanup as a separate change

## Phase 2: Performance Optimizations (Medium Priority)

### ✅ Refactor async processing for blueprints - COMPLETED

- Converted ThreadPoolExecutor to asyncio.gather in data_processors.py
- Improved concurrency and reduced overhead
- Modularized update_blueprint_in_wp into smaller functions

### ✅ Add type hints and input validation - COMPLETED

- Implemented type hints across key Python modules
- Added validation for API data to prevent errors
- Enhanced security and IDE integration

## Phase 3: Testing and Quality Assurance (Medium Priority)

### ✅ Expand test coverage - COMPLETED

- Installed pytest-asyncio and coverage tools (pytest 8.x, pytest-cov)
- Wrote integration tests for API calls and data processing pipelines
- Added async tests for blueprint processing functions
- Configured pytest.ini for coverage reporting

## Phase 4: Tooling and Maintenance (Low Priority)

### ✅ Set up development tooling - COMPLETED

- Added pre-commit hooks for linting and formatting (black, isort, flake8, bandit)
- Updated dependencies to latest stable versions (aiohttp 3.9, pytest 8.x)
- Configured pyproject.toml and .pre-commit-config.yaml

### Modularize code and add benchmarks

- Break down long functions into smaller units
- Add performance decorators for monitoring
- Document scalability improvements

## Notes

- Always check for existing custom post types and fields before creating new ones
- Prioritize speed, simplicity, and security in all changes
- Test changes in a staging environment before production deployment
- Update documentation after each phase completion