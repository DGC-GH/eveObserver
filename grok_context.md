# EVE Observer - Grok Development Context

**This file provides context for future Grok code conversations to build upon previous work and improve the EVE Observer project.**

## Project Status (September 2025)

EVE Observer is a fully functional EVE Online industrial dashboard with the following completed enhancements:

### ✅ **Completed Enhancements**
1. **Configuration Management**: Centralized config.py with environment variable support
2. **Code Organization**: Refactored main() function into focused helper functions
3. **Dashboard Pagination**: JavaScript pagination for large datasets (10 items/page)
4. **Documentation**: Comprehensive README with setup/troubleshooting guides
5. **Testing Framework**: Pytest suite with 9 passing tests

### ✅ **Core Features Implemented**
- **Blueprint Management**: BPO/BPC tracking from multiple sources with ME/TE display
- **Industry Job Monitoring**: Real-time job tracking with 24h completion alerts
- **Planetary Interaction**: Colony management with extraction timer alerts
- **Multi-Character Support**: OAuth authentication for multiple characters
- **WordPress Integration**: ACF-powered custom post types for data storage
- **Automated Updates**: Cron-based daily data refreshes

## Technical Architecture

### Backend Structure
```
scripts/
├── config.py              # Centralized configuration
├── fetch_data.py          # Main data fetching (refactored)
├── esi_oauth.py           # OAuth authentication
├── tests/                 # Pytest test suite
│   ├── test_config.py     # Configuration tests
│   └── test_fetch_data.py # Core function tests
└── requirements.txt       # Dependencies + pytest
```

### Key Functions (Post-Refactoring)
- `collect_corporation_members()` - Token management and grouping
- `process_corporation_data()` - Corporation data processing
- `process_character_data()` - Individual character processing
- `check_industry_job_completions()` - Job completion alerts
- `check_planet_extraction_completions()` - PI extraction alerts

### Frontend Structure
```
js/dashboard.js           # Paginated dashboard with Chart.js
docs/                     # User documentation
├── README.md            # Comprehensive setup guide
└── (other docs)
```

## Recent Development Patterns

### Code Organization Approach
- Break down monolithic functions into focused helpers
- Use descriptive function names with clear responsibilities
- Add comprehensive error handling and logging
- Implement proper separation of concerns

### Testing Strategy
- Unit tests for configuration loading
- Mock external API calls for reliable testing
- Test edge cases and error conditions
- Maintain high test coverage for core functions

### UI/UX Improvements
- Implement pagination for large datasets
- Add real-time timers and alerts
- Ensure responsive design
- Optimize performance with intelligent caching

## Future Enhancement Opportunities

### Potential Areas for Improvement
1. **Performance Optimization**
   - Parallel processing improvements
   - Advanced caching strategies
   - Database query optimization

2. **Feature Expansion**
   - Market data integration
   - Profitability calculators
   - Advanced analytics and reporting

3. **User Experience**
   - Enhanced visualizations
   - Mobile app companion
   - Notification system improvements

4. **Infrastructure**
   - Containerization (Docker)
   - CI/CD pipeline
   - Monitoring and logging improvements

### Development Guidelines for Future Work
- Maintain modular code structure
- Add tests for new features
- Update documentation
- Follow existing patterns and conventions
- Ensure backward compatibility

## Key Files to Reference

### Core Scripts
- `scripts/fetch_data.py` - Main data processing logic
- `scripts/config.py` - Configuration management
- `scripts/esi_oauth.py` - Authentication handling

### Tests
- `scripts/tests/test_config.py` - Configuration testing
- `scripts/tests/test_fetch_data.py` - Core function testing

### Documentation
- `scripts/README.md` - User setup and troubleshooting
- `grok_context.md` - This development context file

## Conversation Continuity Notes

When continuing development:
- Reference completed enhancements to avoid duplication
- Build upon existing helper functions and patterns
- Maintain consistency with current architecture
- Update this context file with new developments
- Ensure all changes include appropriate tests

## Compliance & Ethics

Remember: EVE Observer must remain compliant with CCP policies:
- Read-only ESI API usage only
- No in-game automation
- Manual player actions required
- Out-of-game analysis and optimization only
- **Debugging Results (September 2025)**:
  - Fixed function definition order in fetch_data.py (get_wp_auth called before definition).
  - Dependencies installed (requests, requests-oauthlib, python-dotenv).
  - Scripts run without syntax errors.
  - .env file exists with credentials (needs real ESI app registration if not done).
  - Next: Register ESI app, authorize characters, set up WordPress site with plugin, test data fetching.
  - Fixed token refresh failures (401 errors due to unapproved corporation scopes); reduced to character-only scopes.
  - Updated refresh_token method to use Basic auth instead of Bearer.
  - Fixed null meta values causing post update failures; filtered out nulls.
  - Ensured unique WordPress posts by adding ID-based slugs (character-{id}, blueprint-{item_id}, planet-{planet_id}).
  - Set up daily cron job at 2 AM for automated data fetching.

EVE Observer is a custom web-based dashboard built on WordPress with Advanced Custom Fields (ACF) plugin, integrated with backend scripts for pulling and analyzing data from the EVE Online ESI API. The goal is to streamline passive income activities like BPO research, T2 Planetary Interaction (PI), and related industrial tasks across multiple characters and accounts. This tool provides analytical advantages through data visualization, alerts, and optimization without automating in-game actions, ensuring compliance with CCP’s policies.

The project uses VS Code with GitHub Copilot and Grok Code Fast 1 for rapid development. Scripts will run locally on a Mac Mini (or server) for data fetching, with WordPress handling the frontend UI. All development focuses on out-of-game enhancements to reduce tedium and burnout.

**Key Principles:**

- Use ESI API for read-only data pulls (e.g., blueprints, industry jobs, planets).
- No in-game automation; all interactions remain manual.
- Iterative development: Start with core modules, add features progressively.
- Open for expansion to new activities like reactions or invention.

## Tech Stack

- **Frontend**: WordPress (with ACF for custom fields/posts), Chart.js for visualizations, Bootstrap or similar for UI.
- **Backend/Scripts**: Python (or Node.js) scripts in VS Code for API calls (using requests or axios), cron jobs for periodic updates.
- **API Integration**: EVE ESI (OAuth for multi-character auth).
- **Hosting**: Local Mac Mini for scripts; WordPress site on a server or local for dev.
- **Version Control**: GitHub repo at `eve.observer` (push updates to main/docs branches).
- **Tools**: VS Code + Copilot/Grok Code Fast 1 for code generation; no Macro Recorder for EVE-related tasks.

## Roadmap

The project is divided into phases for manageable implementation. Each phase builds on the previous, with milestones for testing. Use Grok Code Fast 1 to generate code snippets based on phase descriptions.

### Phase 1: Setup and Core Infrastructure (1-2 weeks)

- **Goal**: Establish the foundation for API integration and basic dashboard.
- **Steps**:
1. Set up WordPress site with ACF plugin; create custom post types (e.g., “Character”, “Blueprint”, “Planet”).
2. Implement ESI OAuth flow in a Python script (handle multi-character tokens).
3. Create a basic data fetcher script to pull character lists and store in WP database via REST API.
4. Build a login-protected dashboard page in WP to display aggregated character data.
- **Milestones**: Successful API auth for all 9 characters; basic WP page showing character names/skills.
- **Features**:
  - User auth in WP tied to ESI (optional: simple WP users for now).
  - Cron script on Mac Mini to refresh data daily.

### Phase 2: BPO Research Module (2-3 weeks)

- **Goal**: Streamline BPO research tracking and optimization.
- **Steps**:
1. Extend fetcher script to pull blueprints (`/characters/{id}/blueprints/`) and industry jobs (`/characters/{id}/industry/jobs/`).
2. Use ACF to create fields for BPO details (ME/TE levels, job status, completion times).
3. Code visualization components (e.g., timelines with Chart.js).
4. Add alert system: Script checks job endings, sends emails via smtplib or webhooks.
5. Integrate market data pull (`/markets/{region_id}/orders/`) for profit estimates.
- **Milestones**: Dashboard shows real-time job queues; alerts notify on completions.
- **Features per Functionality**:
  - **Job Tracking**: Timeline view of active researches; filter by character/BPO type (capital components).
  - **Profit Calculator**: Input BPO type, output estimated sell price via contracts/market history.
  - **Alerts**: Email/Discord notifications for job ends or slot availability.
  - **Sales Tracker**: Pull corp contracts (`/corporations/{id}/contracts/`); suggest pricing based on trends.

### Phase 3: T2 PI Module (2-3 weeks)

- **Goal**: Manage PI colonies in Kino with reminders and optimizations.
- **Steps**:
1. Add API pulls for planets (`/characters/{id}/planets/`) and details (`/characters/{id}/planets/{planet_id}/`).
2. Use ACF for planet custom posts (fields: resources, extractors, factories, timers).
3. Develop visual mapper (e.g., simple SVG or canvas for planet layouts).
4. Implement timer checks in scripts for expiry alerts.
5. Add profitability tracker linking to market API for T2 outputs.
- **Milestones**: WP page displays all colonies; alerts for extractor resets.
- **Features per Functionality**:
  - **Colony Mapper**: Interactive view of planets in Kino system; highlight resource chains for T2 PI.
  - **Timer Reminders**: Notifications for cycle ends; predictive depletion forecasts.
  - **Profitability Tracker**: ISK/hour calculations; suggest chain adjustments.
  - **Multi-Character Sync**: Aggregated overview of all 9 characters’ PI setups.

### Phase 4: Additional Activities and Integrations (3-4 weeks)

- **Goal**: Expand to new income streams with synergies.
- **Steps**:
1. For Reaction Farming: Extend industry module to handle reaction jobs; add simulator scripts.
2. For Invention: Pull invention data; code probability calculators.
3. For Market Speculation: Dedicated trading page with alerts on price spikes.
4. Integrate cross-module data (e.g., feed PI outputs into invention calcs).
5. Add export/import features (CSV for manual tweaks).
- **Milestones**: New modules functional; end-to-end workflow from PI to market sales.
- **Features per Functionality**:
  - **Reaction Farming**: Chain simulators; material requirement trackers.
  - **Invention for T2 BPCs**: Success probability tools; batch planning.
  - **Market Speculation**: Alert system for buy/sell opportunities; trend visualizations.
  - **Synergies**: Automated reports linking BPO/PI to other activities.

### Phase 5: Polish, Testing, and Iteration (Ongoing, 1-2 weeks initially)

- **Goal**: Ensure reliability and add advanced features.
- **Steps**:
1. Test with dummy data; then live ESI pulls.
2. Optimize for performance (e.g., cache API responses).
3. Add user feedback loops (e.g., WP forms for feature requests).
4. Document code in repo (inline comments via Copilot).
5. Iterate based on usage: Use Grok Code Fast 1 for quick additions like ML predictions (local libs only).
- **Milestones**: Bug-free deployment; first production use.
- **Features**:
  - Security: API token encryption.
  - UI Enhancements: Mobile-responsive dashboards.
  - Extensibility: Plugin architecture for new ESI endpoints.

## Implementation Guidelines for Grok Code Fast 1

- **Prompt Structure**: When using Grok Code Fast 1, provide phase-specific prompts like: “Generate Python script to fetch ESI blueprints data and post to WordPress REST API. Include OAuth handling.”
- **Best Practices**: Break into small functions; test in VS Code REPL; commit to GitHub after each feature.
- **Risks/Mitigations**: Rate limit API calls (ESI has limits); handle errors gracefully. Always manual in-game actions.
- **Resources**: Reference ESI docs (https://esi.evetech.net/ui/), WP ACF guides, and awesome-eve GitHub list for inspiration.

## Current Status (September 2025)

- **Code Development**: All core scripts and WordPress plugin written and debugged.
- **Setup Progress**: WordPress site with free ACF plugin set up, ESI OAuth and data fetcher scripts ready.
- **Authorization**: ESI application registered, characters authorized.
- **Issues Fixed**: Function order in fetch_data.py, dependencies installed, token refresh, null meta handling, unique post slugs, cron automation.
- **Next Steps**: 
  - Test dashboard display with live data.
  - Monitor automated data refreshes.
  - Begin Phase 2: BPO Research Module.
- **Progress**: Phase 1 complete, data fetching automated, ready for feature expansion.