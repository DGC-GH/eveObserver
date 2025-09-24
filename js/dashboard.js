// EVE Observer Dashboard - Modern JavaScript
console.log('EVE Observer Dashboard script loaded');

class EVEDashboard {
    constructor() {
        console.log('EVEDashboard constructor called');
        this.currentPage = {
            blueprints: 1,
            planets: 1
        };
        this.itemsPerPage = 10;
        this.data = {
            characters: [],
            blueprints: [],
            planets: [],
            corporations: [],
            contracts: []
        };
        this.filteredData = { ...this.data };
        this.searchTimeouts = {};
        this.searchTimeouts.logs = null;
        this.postTypeMap = {
            characters: 'eve_character',
            blueprints: 'eve_blueprint',
            planets: 'eve_planet',
            corporations: 'eve_corporation',
            contracts: 'eve_contract'
        };
        this.syncStatusInterval = null;

        this.init();
    }

    async init() {
        console.log('🔄 [INIT] EVEDashboard init called');
        console.log('🔄 [INIT] DOM ready state:', document.readyState);
        try {
            console.log('🔄 [INIT] Starting loadAllData()...');
            await this.loadAllData();
            console.log('✅ [INIT] loadAllData() completed');
        } catch (error) {
            console.error('❌ [INIT ERROR] loadAllData() failed:', error);
            console.log('🔄 [INIT] Continuing with empty data...');
        }

        try {
            console.log('🔄 [INIT] Starting setupSearch()...');
            this.setupSearch();
            console.log('✅ [INIT] setupSearch() completed');
        } catch (error) {
            console.error('❌ [INIT ERROR] setupSearch() failed:', error);
        }

        try {
            console.log('🔄 [INIT] Starting setupCardClicks()...');
            this.setupCardClicks();
            console.log('✅ [INIT] setupCardClicks() completed');
        } catch (error) {
            console.error('❌ [INIT ERROR] setupCardClicks() failed:', error);
        }

        try {
            console.log('🔄 [INIT] Starting renderChart()...');
            this.renderChart();
            console.log('✅ [INIT] renderChart() completed');
        } catch (error) {
            console.error('❌ [INIT ERROR] renderChart() failed:', error);
        }

        try {
            console.log('🔄 [INIT] Starting renderAllTables()...');
            this.renderAllTables();
            console.log('✅ [INIT] renderAllTables() completed');
        } catch (error) {
            console.error('❌ [INIT ERROR] renderAllTables() failed:', error);
        }

        try {
            console.log('🔄 [INIT] Starting setupActionButtons()...');
            this.setupActionButtons();
            console.log('✅ [INIT] setupActionButtons() completed');
        } catch (error) {
            console.error('❌ [INIT ERROR] setupActionButtons() failed:', error);
        }

        try {
            console.log('🔄 [INIT] Starting hideLoaders()...');
            this.hideLoaders();
            console.log('✅ [INIT] hideLoaders() completed');
        } catch (error) {
            console.error('❌ [INIT ERROR] hideLoaders() failed:', error);
        }

        try {
            console.log('🔄 [INIT] Checking for existing sync on page load...');
            const initialStatus = await this.checkSyncStatus();
            if (initialStatus.running) {
                console.log('🔄 [INIT] Found existing sync running, updating display...');
                this.updateSyncStatusDisplay(initialStatus);
            }
            console.log('✅ [INIT] Initial sync status check completed');
        } catch (error) {
            console.error('❌ [INIT ERROR] Initial sync status check failed:', error);
        }

        console.log('🎉 [INIT] Dashboard initialization completed (with error handling)');
    }

    async loadAllData() {
        const sections = ['characters', 'blueprints', 'planets', 'corporations', 'contracts'];

        for (const section of sections) {
            try {
                const url = `/wp-json/wp/v2/${this.postTypeMap[section]}?per_page=100&_embed`;
                const response = await fetch(url);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();

                this.data[section] = Array.isArray(data) ? data : [];
                this.filteredData[section] = [...this.data[section]];

                console.log(`Loaded ${this.data[section].length} ${section}`);
            } catch (error) {
                console.error(`Error loading ${section}:`, error);
                this.data[section] = [];
                this.filteredData[section] = [];
            }
        }

        console.log('All data loaded');
    }

    setupSearch() {
        const searchIds = ['characters-search', 'blueprints-search', 'planets-search', 'corporations-search', 'contracts-search'];

        searchIds.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('input', (e) => {
                    const section = id.replace('-search', '');
                    this.debouncedSearch(section, e.target.value);
                });
            }
        });

        // Setup sorting
        this.setupSorting();
    }

    setupSorting() {
        const tableIds = ['characters-table', 'blueprints-table', 'planets-table', 'corporations-table', 'contracts-table'];

        tableIds.forEach(tableId => {
            const table = document.getElementById(tableId);
            if (!table) return;

            const headers = table.querySelectorAll('th');
            headers.forEach((header, index) => {
                header.style.cursor = 'pointer';
                header.style.userSelect = 'none';
                header.addEventListener('click', () => {
                    const section = tableId.replace('-table', '');
                    this.sortTable(section, index);
                });

                // Add sort indicator
                const indicator = document.createElement('span');
                indicator.className = 'sort-indicator';
                indicator.innerHTML = ' ↕️';
                indicator.style.marginLeft = '4px';
                header.appendChild(indicator);
            });
        });
    }

    sortTable(section, columnIndex) {
        const tbody = document.getElementById(`${section}-tbody`);
        if (!tbody) return;

        const rows = Array.from(tbody.querySelectorAll('tr'));
        const sortKey = this.getSortKey(section, columnIndex);

        // Toggle sort direction
        if (this.currentSort?.section === section && this.currentSort?.column === columnIndex) {
            this.currentSort.direction = this.currentSort.direction === 'asc' ? 'desc' : 'asc';
        } else {
            this.currentSort = { section, column: columnIndex, direction: 'asc' };
        }

        rows.sort((a, b) => {
            const aValue = this.getCellValue(a, columnIndex, sortKey);
            const bValue = this.getCellValue(b, columnIndex, sortKey);

            let comparison = 0;
            if (aValue < bValue) comparison = -1;
            if (aValue > bValue) comparison = 1;

            return this.currentSort.direction === 'desc' ? -comparison : comparison;
        });

        // Re-append sorted rows
        rows.forEach(row => tbody.appendChild(row));

        // Update sort indicators
        this.updateSortIndicators(section, columnIndex);
    }

    getSortKey(section, columnIndex) {
        const sortKeys = {
            characters: ['title', 'corporation', 'alliance', 'security', 'location'],
            blueprints: ['title', 'typeId', 'location', 'me', 'te', 'runs'],
            planets: ['title', 'type', 'level', 'system', 'pins'],
            corporations: ['title', 'ticker', 'members', 'tax', 'balance'],
            contracts: ['title', 'type', 'status', 'price', 'competing_price', 'outbid']
        };
        return sortKeys[section]?.[columnIndex] || 'title';
    }

    getCellValue(row, columnIndex, sortKey) {
        const cell = row.cells[columnIndex];
        if (!cell) return '';

        const text = cell.textContent.trim();

        // Handle numeric values
        if (['me', 'te', 'level', 'members', 'tax', 'runs', 'pins'].includes(sortKey)) {
            const num = parseFloat(text.replace(/[^\d.-]/g, ''));
            return isNaN(num) ? 0 : num;
        }

        // Handle ISK values
        if (sortKey === 'price' || sortKey === 'balance' || sortKey === 'competing_price') {
            return this.parseISK(text);
        }

        // Handle security status
        if (sortKey === 'security') {
            const num = parseFloat(text);
            return isNaN(num) ? 0 : num;
        }

        return text.toLowerCase();
    }

    parseISK(text) {
        const match = text.match(/([\d.]+)\s*(K|M|B)?/);
        if (!match) return 0;

        const num = parseFloat(match[1]);
        const unit = match[2];

        switch (unit) {
            case 'K': return num * 1000;
            case 'M': return num * 1000000;
            case 'B': return num * 1000000000;
            default: return num;
        }
    }

    setupActionButtons() {
        console.log('🔄 [SETUP] setupActionButtons called');
        const copyOutbidBtn = document.getElementById('copy-outbid-contracts');
        console.log('🔄 [SETUP] copyOutbidBtn found:', !!copyOutbidBtn);
        if (copyOutbidBtn) {
            console.log('🔄 [SETUP] Adding event listener to copy button');
            copyOutbidBtn.addEventListener('click', () => {
                console.log('🔄 [SETUP] Copy button clicked');
                this.copyOutbidContracts();
            });
            console.log('✅ [SETUP] Copy button event listener added');
        } else {
            console.log('⚠️ [SETUP] Copy button not found');
        }

        // Setup log viewer buttons
        this.setupLogViewerButtons();
    }

    setupLogViewerButtons() {
        console.log('🔄 [SETUP] setupLogViewerButtons called');

        // Refresh logs button
        const refreshLogsBtn = document.getElementById('refresh-logs');
        if (refreshLogsBtn) {
            refreshLogsBtn.addEventListener('click', () => {
                console.log('🔄 [LOGS] Refresh logs button clicked');
                this.refreshLogs();
            });
            console.log('✅ [SETUP] Refresh logs button event listener added');
        }

        // Clear logs button
        const clearLogsBtn = document.getElementById('clear-logs');
        if (clearLogsBtn) {
            clearLogsBtn.addEventListener('click', () => {
                console.log('🔄 [LOGS] Clear logs button clicked');
                this.clearLogs();
            });
            console.log('✅ [SETUP] Clear logs button event listener added');
        }

        // Search logs input
        const searchLogsInput = document.getElementById('logs-search');
        if (searchLogsInput) {
            searchLogsInput.addEventListener('input', (e) => {
                console.log('🔄 [LOGS] Search logs input changed:', e.target.value);
                this.debouncedSearchLogs(e.target.value);
            });
            console.log('✅ [SETUP] Search logs input event listener added');
        }

        // Log level filter checkboxes
        const logLevelCheckboxes = document.querySelectorAll('input[id^="log-filter-"]');
        logLevelCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                console.log('🔄 [LOGS] Log level filter changed:', checkbox.id, checkbox.checked);
                this.filterLogsByLevel();
            });
        });
        console.log('✅ [SETUP] Log level filter checkboxes event listeners added');

        // Load logs on page load
        this.refreshLogs();
    }

    async refreshLogs() {
        console.log('🔄 [LOGS] refreshLogs called');

        const refreshBtn = document.getElementById('refresh-logs');
        const originalText = refreshBtn ? refreshBtn.innerHTML : '';
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<span class="dashicons dashicons-update dashicons-spin"></span> Loading...';
        }

        try {
            const logs = await this.getLogs();
            this.displayLogs(logs);
            this.showNotification('Logs refreshed successfully', 'success');
        } catch (error) {
            console.error('❌ [LOGS] Error refreshing logs:', error);
            this.showNotification('Failed to refresh logs: ' + error.message, 'error');
        } finally {
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = originalText;
            }
        }
    }

    async clearLogs() {
        console.log('🔄 [LOGS] clearLogs called');

        if (!confirm('Are you sure you want to clear all logs? This action cannot be undone.')) {
            return;
        }

        const clearBtn = document.getElementById('clear-logs');
        const originalText = clearBtn ? clearBtn.innerHTML : '';
        if (clearBtn) {
            clearBtn.disabled = true;
            clearBtn.innerHTML = '<span class="dashicons dashicons-update dashicons-spin"></span> Clearing...';
        }

        try {
            const response = await this.makeAjaxRequest({
                action: 'eve_clear_logs',
                nonce: eveObserverApi.nonce
            });

            if (response.success) {
                this.displayLogs([]);
                this.showNotification('Logs cleared successfully', 'success');
            } else {
                throw new Error(response.data?.message || 'Failed to clear logs');
            }
        } catch (error) {
            console.error('❌ [LOGS] Error clearing logs:', error);
            this.showNotification('Failed to clear logs: ' + error.message, 'error');
        } finally {
            if (clearBtn) {
                clearBtn.disabled = false;
                clearBtn.innerHTML = originalText;
            }
        }
    }

    async getLogs(search = '', levels = []) {
        console.log('🔄 [LOGS] getLogs called with search:', search, 'levels:', levels);

        return new Promise((resolve, reject) => {
            jQuery.ajax({
                url: eveObserverApi.ajaxUrl,
                type: 'POST',
                data: {
                    action: 'eve_get_logs',
                    nonce: eveObserverApi.nonce,
                    search: search,
                    levels: levels.join(',')
                },
                timeout: 30000,
                success: (response) => {
                    console.log('✅ [LOGS] Get logs successful:', response);
                    if (response.success && response.data) {
                        resolve(response.data.logs || []);
                    } else {
                        resolve([]);
                    }
                },
                error: (xhr, status, error) => {
                    console.error('❌ [LOGS] Get logs failed:', xhr.status, error);
                    reject(new Error(xhr.responseJSON?.data?.message || error || 'Failed to get logs'));
                }
            });
        });
    }

    displayLogs(logs) {
        console.log('🔄 [LOGS] displayLogs called with', logs.length, 'logs');

        const logsContainer = document.getElementById('logs-display');
        if (!logsContainer) {
            console.error('❌ [LOGS] Logs container not found');
            return;
        }

        if (!logs || logs.length === 0) {
            logsContainer.innerHTML = '<div class="eve-no-logs">No logs found</div>';
            return;
        }

        const logsHtml = logs.map(log => {
            const levelClass = `eve-log-${log.level.toLowerCase()}`;
            const timestamp = new Date(log.timestamp).toLocaleString();
            return `
                <div class="eve-log-entry ${levelClass}">
                    <span class="eve-log-timestamp">${timestamp}</span>
                    <span class="eve-log-level">${log.level}</span>
                    <span class="eve-log-message">${this.escapeHtml(log.message)}</span>
                </div>
            `;
        }).join('');

        logsContainer.innerHTML = logsHtml;

        // Scroll to bottom to show latest logs
        logsContainer.scrollTop = logsContainer.scrollHeight;
    }

    debouncedSearchLogs(query) {
        clearTimeout(this.searchTimeouts.logs);
        this.searchTimeouts.logs = setTimeout(() => {
            this.searchLogs(query);
        }, 300);
    }

    async searchLogs(query) {
        console.log('🔄 [LOGS] searchLogs called with query:', query);

        const levels = this.getSelectedLogLevels();
        try {
            const logs = await this.getLogs(query, levels);
            this.displayLogs(logs);
        } catch (error) {
            console.error('❌ [LOGS] Error searching logs:', error);
            this.showNotification('Failed to search logs: ' + error.message, 'error');
        }
    }

    async filterLogsByLevel() {
        console.log('🔄 [LOGS] filterLogsByLevel called');

        const searchInput = document.getElementById('search-logs');
        const query = searchInput ? searchInput.value : '';
        const levels = this.getSelectedLogLevels();

        try {
            const logs = await this.getLogs(query, levels);
            this.displayLogs(logs);
        } catch (error) {
            console.error('❌ [LOGS] Error filtering logs:', error);
            this.showNotification('Failed to filter logs: ' + error.message, 'error');
        }
    }

    getSelectedLogLevels() {
        const checkboxes = document.querySelectorAll('input[id^="log-filter-"]:checked');
        return Array.from(checkboxes).map(cb => cb.id.replace('log-filter-', '').toUpperCase());
    }

    setupCardClicks() {
        console.log('🔄 [SETUP] setupCardClicks called');
        const cards = document.querySelectorAll('.eve-card-clickable');
        console.log('🔄 [SETUP] Found cards:', cards.length);
        cards.forEach(card => {
            card.addEventListener('click', (e) => {
                // Don't trigger card click if sync button was clicked
                if (e.target.closest('.eve-sync-btn')) {
                    return;
                }
                const section = card.getAttribute('data-section');
                console.log('🔄 [SETUP] Card clicked, section:', section);
                this.scrollToSection(section);
            });
        });

        // Setup sync button clicks
        console.log('🔄 [SETUP] About to call setupSyncButtons()...');
        this.setupSyncButtons();
        console.log('✅ [SETUP] setupSyncButtons() completed from setupCardClicks');
    }

    setupSyncButtons() {
        console.log('🔄 [INIT STEP 1] setupSyncButtons called');

        const syncButtons = document.querySelectorAll('.eve-sync-btn');
        const syncAllButton = document.getElementById('eve-sync-all');

        console.log('🔄 [INIT STEP 2] Found sync buttons:', syncButtons.length);
        console.log('🔄 [INIT STEP 3] Sync all button found:', !!syncAllButton);

        if (syncAllButton) {
            console.log('🔄 [INIT STEP 4] Sync all button element:', syncAllButton);
            console.log('🔄 [INIT STEP 5] Sync all button HTML:', syncAllButton.outerHTML);
        } else {
            console.error('❌ [INIT ERROR] Sync all button not found!');
        }

        console.log('🔄 [INIT STEP 6] Checking eveObserverApi availability...');
        console.log('🔄 [INIT STEP 7] eveObserverApi available:', typeof eveObserverApi !== 'undefined');
        if (typeof eveObserverApi !== 'undefined') {
            console.log('🔄 [INIT STEP 8] eveObserverApi.nonce:', eveObserverApi.nonce ? 'present' : 'missing');
            console.log('🔄 [INIT STEP 9] eveObserverApi.ajaxUrl:', eveObserverApi.ajaxUrl);
            console.log('🔄 [INIT STEP 10] Full eveObserverApi object:', eveObserverApi);
        } else {
            console.error('❌ [INIT ERROR] eveObserverApi is not defined! This will prevent sync from working.');
        }

        console.log('🔄 [INIT STEP 11] Checking jQuery availability...');
        console.log('🔄 [INIT STEP 12] jQuery available:', typeof jQuery !== 'undefined');
        if (typeof jQuery !== 'undefined') {
            console.log('🔄 [INIT STEP 13] jQuery version:', jQuery.fn.jquery);
        }

        console.log('🔄 [INIT STEP 14] Setting up individual sync button event listeners...');
        syncButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const section = button.getAttribute('data-section');
                console.log('🔄 [INDIVIDUAL SYNC] Sync button clicked for section:', section);
                this.syncSection(section, button);
            });
        });
        console.log('✅ [INIT STEP 15] Individual sync button listeners set up');

        console.log('🔄 [INIT STEP 16] Setting up sync all button event listener...');
        if (syncAllButton) {
            syncAllButton.addEventListener('click', (e) => {
                console.log('🔄 [STEP 1] Sync All button clicked - event detected!');
                console.log('🔄 [STEP 2] Event object:', e);
                console.log('🔄 [STEP 3] Button element:', syncAllButton);
                console.log('🔄 [STEP 4] Button data-section:', syncAllButton.getAttribute('data-section'));
                console.log('🔄 [STEP 5] eveObserverApi available:', typeof eveObserverApi !== 'undefined');
                if (typeof eveObserverApi !== 'undefined') {
                    console.log('🔄 [STEP 6] eveObserverApi.nonce exists:', !!eveObserverApi.nonce);
                    console.log('🔄 [STEP 7] eveObserverApi.ajaxUrl exists:', !!eveObserverApi.ajaxUrl);
                }
                this.syncSection('all', syncAllButton);
            });
            console.log('✅ [INIT STEP 17] Sync all button event listener set up');
        } else {
            console.error('❌ [INIT ERROR] Sync all button not found!');
        }

        console.log('🔄 [INIT STEP 18] Setting up test logging button event listener...');
        const testLoggingButton = document.getElementById('eve-test-logging');
        if (testLoggingButton) {
            testLoggingButton.addEventListener('click', (e) => {
                console.log('🔄 [TEST LOGGING] Test logging button clicked!');
                console.log('🔄 [TEST LOGGING] Current timestamp:', new Date().toISOString());
                console.log('🔄 [TEST LOGGING] eveObserverApi available:', typeof eveObserverApi !== 'undefined');
                if (typeof eveObserverApi !== 'undefined') {
                    console.log('🔄 [TEST LOGGING] eveObserverApi object:', eveObserverApi);
                }
                console.log('🔄 [TEST LOGGING] jQuery available:', typeof jQuery !== 'undefined');
                if (typeof jQuery !== 'undefined') {
                    console.log('🔄 [TEST LOGGING] jQuery version:', jQuery.fn.jquery);
                }
                console.log('🔄 [TEST LOGGING] Dashboard instance:', this);
                console.log('🔄 [TEST LOGGING] Test completed successfully!');
                this.showNotification('Test logging completed - check console for details', 'success');
            });
            console.log('✅ [INIT STEP 19] Test logging button event listener set up');
        } else {
            console.error('❌ [INIT ERROR] Test logging button not found!');
        }

        console.log('🔄 [INIT STEP 20] Setting up test API button event listener...');
        const testApiButton = document.getElementById('eve-test-api');
        if (testApiButton) {
            testApiButton.addEventListener('click', async (e) => {
                console.log('🔄 [TEST API] Test API button clicked!');
                try {
                    console.log('🔄 [TEST API] Making test API call...');
                    const response = await fetch('/wp-json/eve-observer/v1/test');
                    console.log('🔄 [TEST API] Response status:', response.status);
                    const data = await response.json();
                    console.log('🔄 [TEST API] Response data:', data);
                    this.showNotification('Test API call successful - check console', 'success');
                } catch (error) {
                    console.error('❌ [TEST API] Error:', error);
                    this.showNotification('Test API call failed - check console', 'error');
                }
            });
            console.log('✅ [INIT STEP 21] Test API button event listener set up');
        } else {
            console.log('⚠️ [INIT WARNING] Test API button not found (this is optional)');
        }

        // Set up stop sync button
        const stopSyncButton = document.getElementById('stop-sync-button');
        if (stopSyncButton) {
            stopSyncButton.addEventListener('click', () => {
                console.log('🔄 [STOP SYNC] Stop sync button clicked');
                this.stopSync();
            });
            console.log('✅ [INIT STEP 22] Stop sync button event listener set up');
        } else {
            console.log('⚠️ [INIT WARNING] Stop sync button not found');
        }

        // Start status polling with a delay to ensure AJAX actions are registered
        setTimeout(() => {
            this.startSyncStatusPolling();
        }, 2000); // Wait 2 seconds before starting polling
        console.log('✅ [INIT STEP 23] Sync status polling will start in 2 seconds');
    }

    // Sync status management methods
    async checkSyncStatus() {
        return new Promise((resolve, reject) => {
            console.log('🔄 [SYNC STATUS] Checking sync status via AJAX...');

            if (typeof jQuery === 'undefined') {
                console.error('❌ [SYNC STATUS] jQuery is not available!');
                resolve({ running: false, progress: 0, message: 'jQuery not available' });
                return;
            }

            jQuery.ajax({
                url: eveObserverApi.ajaxUrl,
                type: 'POST',
                data: {
                    action: 'eve_sync_status',
                    nonce: eveObserverApi.nonce
                },
                timeout: 30000, // Increased from 10 seconds to 30 seconds
                success: (response) => {
                    console.log('✅ [SYNC STATUS] Status check successful:', response);
                    if (response.success && response.data) {
                        resolve(response.data);
                    } else {
                        resolve({ running: false, progress: 0, message: 'No sync running' });
                    }
                },
                error: (xhr, status, error) => {
                    console.error('❌ [SYNC STATUS] Status check failed:', xhr.status, error);
                    // Don't reject on timeout - just resolve with error status
                    if (status === 'timeout') {
                        resolve({ running: false, progress: 0, message: 'Status check timed out - sync may still be running' });
                    } else {
                        resolve({ running: false, progress: 0, message: 'Unable to check status: ' + error });
                    }
                }
            });
        });
    }

    async checkSectionSyncStatus(section) {
        // For now, just check if any sync is running - in the future this could be section-specific
        return await this.checkSyncStatus();
    }

    updateSyncStatusDisplay(status) {
        const statusDiv = document.getElementById('sync-status-display');
        const progressBar = document.getElementById('sync-status-progress');
        const progressFill = document.querySelector('#sync-status-progress .eve-progress-fill');
        const statusText = document.getElementById('sync-status-text');
        const stopButton = document.getElementById('stop-sync-button');
        const stageProgressDiv = document.getElementById('sync-stage-progress');

        if (!statusDiv || !progressBar || !progressFill || !statusText) {
            console.log('⚠️ [SYNC STATUS] Status display elements not found');
            return;
        }

        if (status.running) {
            statusDiv.style.display = 'block';
            progressFill.style.width = `${status.progress || 0}%`;
            statusText.textContent = status.message || 'Sync in progress...';

            // Show stop button if sync is running
            if (stopButton) {
                stopButton.style.display = 'inline-block';
            }

            // Update stage progress bars if stages data is available
            if (status.stages && stageProgressDiv) {
                stageProgressDiv.style.display = 'block';
                this.updateStageProgressBars(status.stages);
            } else if (stageProgressDiv) {
                stageProgressDiv.style.display = 'none';
            }
        } else {
            statusDiv.style.display = 'none';
            if (stopButton) {
                stopButton.style.display = 'none';
            }
            if (stageProgressDiv) {
                stageProgressDiv.style.display = 'none';
            }
        }
    }

    updateStageProgressBars(stages) {
        console.log('🔄 [STAGE PROGRESS] Updating stage progress bars:', stages);

        // Clear existing stage containers
        const stageProgressDiv = document.getElementById('sync-stage-progress');
        if (!stageProgressDiv) return;

        // Remove existing stage containers (keep the header)
        const existingStages = stageProgressDiv.querySelectorAll('.sync-stage');
        existingStages.forEach(stage => stage.remove());

        // Create stage containers for each stage
        Object.entries(stages).forEach(([stageName, stageData]) => {
            const stageDiv = document.createElement('div');
            stageDiv.className = 'sync-stage';
            stageDiv.innerHTML = `
                <div class="sync-stage-header">
                    <span class="sync-stage-name">${this.formatStageName(stageName)}</span>
                    <span class="sync-stage-status" data-status="${stageData.status || 'pending'}">${this.formatStageStatus(stageData.status || 'pending')}</span>
                </div>
                <div class="eve-progress-bar">
                    <div class="eve-progress-fill" style="width: ${stageData.progress || 0}%"></div>
                </div>
                <div class="sync-stage-message">${stageData.message || ''}</div>
            `;

            stageProgressDiv.appendChild(stageDiv);
        });
    }

    formatStageName(stageName) {
        return stageName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    formatStageStatus(status) {
        const statusMap = {
            pending: 'Pending',
            running: 'Running',
            completed: 'Completed',
            error: 'Error'
        };
        return statusMap[status] || status;
    }

    startSyncStatusPolling() {
        console.log('🔄 [SYNC STATUS] Starting status polling...');
        this.stopSyncStatusPolling(); // Clear any existing polling

        this.syncStatusInterval = setInterval(async () => {
            const status = await this.checkSyncStatus();
            this.updateSyncStatusDisplay(status);
        }, 30000); // Poll every 30 seconds (increased from 10)
    }

    stopSyncStatusPolling() {
        if (this.syncStatusInterval) {
            console.log('🔄 [SYNC STATUS] Stopping status polling...');
            clearInterval(this.syncStatusInterval);
            this.syncStatusInterval = null;
        }
    }

    async stopSync() {
        return new Promise((resolve, reject) => {
            console.log('🔄 [SYNC STOP] Attempting to stop sync via AJAX...');

            if (typeof jQuery === 'undefined') {
                console.error('❌ [SYNC STOP] jQuery is not available!');
                reject(new Error('jQuery not available'));
                return;
            }

            jQuery.ajax({
                url: eveObserverApi.ajaxUrl,
                type: 'POST',
                data: {
                    action: 'eve_stop_sync',
                    nonce: eveObserverApi.nonce
                },
                timeout: 10000,
                success: (response) => {
                    console.log('✅ [SYNC STOP] Stop sync result:', response);
                    if (response.success) {
                        this.showNotification('Sync stopped successfully', 'success');
                        resolve(response);
                    } else {
                        reject(new Error(response.data?.message || 'Failed to stop sync'));
                    }
                },
                error: (xhr, status, error) => {
                    console.error('❌ [SYNC STOP] Stop sync failed:', xhr.status, error);
                    const errorMessage = xhr.responseJSON?.data?.message || error || 'Failed to stop sync';
                    this.showNotification(`Failed to stop sync: ${errorMessage}`, 'error');
                    reject(new Error(errorMessage));
                }
            });
        });
    }

    async syncSection(section, button) {
        console.log(`🔄 [SYNC START] ========================================`);
        console.log(`🔄 [SYNC START] syncSection called with section: ${section}`);
        console.log(`🔄 [SYNC START] Button element:`, button);
        console.log(`🔄 [SYNC START] Button exists:`, !!button);
        console.log(`🔄 [SYNC START] Current timestamp:`, new Date().toISOString());
        console.log(`🔄 [SYNC START] ========================================`);

        console.log(`🔄 [STEP 5] EVE Observer: Starting sync for section: ${section}`);
        console.log(`🔄 [STEP 6] Button element:`, button);
        console.log(`🔄 [STEP 7] Button original text:`, button.innerHTML);

        // Check if sync is already running for this section
        const sectionStatus = await this.checkSectionSyncStatus(section);
        if (sectionStatus.running) {
            this.showNotification(`${section} sync is already running. Please wait for it to complete.`, 'error');
            return;
        }

        // Show progress area for this section
        const progressContainer = document.getElementById('sync-progress-container');
        const progressItem = document.getElementById(`sync-progress-${section}`);
        const progressFill = document.getElementById(`sync-progress-${section}-fill`);
        const progressText = document.getElementById(`sync-progress-${section}-text`);
        const progressContent = document.getElementById(`sync-progress-${section}-content`);

        if (progressContainer) progressContainer.style.display = 'block';
        if (progressItem) progressItem.style.display = 'block';
        if (progressContent) progressContent.textContent = `Starting sync for ${section}...\n`;
        if (progressFill) progressFill.style.width = '0%';
        if (progressText) progressText.textContent = 'Initializing...';

        console.log('🔄 [STEP 8] Checking eveObserverApi availability...');
        console.log('🔄 [STEP 9] eveObserverApi available at sync time:', typeof eveObserverApi !== 'undefined');

        if (typeof eveObserverApi === 'undefined') {
            console.error('❌ [ERROR] eveObserverApi is not defined!');
            if (progressContent) progressContent.textContent += '❌ API configuration error - please refresh the page\n';
            if (progressFill) progressFill.style.width = '100%';
            if (progressFill) progressFill.style.backgroundColor = '#dc3545';
            if (progressText) progressText.textContent = 'Error: API not configured';
            console.log('❌ [STEP 10] Showing error notification...');
            this.showNotification('API configuration error - please refresh the page', 'error');
            return;
        }

        console.log('✅ [STEP 11] eveObserverApi is available');
        console.log('🔄 [STEP 12] API configuration:', {
            nonce: eveObserverApi.nonce ? 'present' : 'missing',
            ajaxUrl: eveObserverApi.ajaxUrl
        });

        // Disable button and show loading state
        console.log('🔄 [STEP 13] Disabling button and setting loading state...');
        const originalText = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="dashicons dashicons-update dashicons-spin"></span> Starting...';
        console.log('✅ [STEP 14] Button disabled and loading state set');

        // Start progress animation
        this.animateProgress(progressFill, progressText, 'Preparing request...');

        try {
            console.log(`🔄 [STEP 15] Preparing AJAX request to start sync ${section}`);
            console.log('🔄 [STEP 16] AJAX action: eve_sync');
            console.log('🔄 [STEP 17] Nonce:', eveObserverApi.nonce);

            const ajaxData = {
                action: 'eve_sync',
                section: section,
                nonce: eveObserverApi.nonce
            };
            console.log('🔄 [STEP 18] AJAX data:', ajaxData);

            console.log(`🔄 [STEP 19] Making AJAX request to start sync ${section}`);
            const response = await this.makeAjaxRequest(ajaxData);
            console.log('✅ [STEP 20] AJAX request completed');
            console.log('🔄 [STEP 21] Response success:', response.success);

            if (response.success) {
                console.log('✅ [STEP 22] Sync started successfully');
                const message = `Sync started successfully for ${section}`;
                console.log('🔄 [STEP 23] Success message:', message);
                console.log('🔄 [STEP 24] Showing success notification...');
                this.showNotification(message, 'success');

                // Show sync output in progress area
                if (progressContent) progressContent.textContent += `✅ Sync started successfully!\n\nThe sync is now running in the background. Progress will be updated automatically.\n`;

                // Update progress to show it's started
                if (progressFill) progressFill.style.width = '10%';
                if (progressFill) progressFill.style.backgroundColor = '#28a745';
                if (progressText) progressText.textContent = 'Sync started - monitoring progress...';

                // Start monitoring progress immediately
                console.log('🔄 [STEP 25] Starting progress monitoring...');
                this.startProgressMonitoring(section, progressFill, progressText, progressContent, button, originalText);

            } else {
                console.log('❌ [STEP 26] Sync start failed');
                if (progressContent) progressContent.textContent += `❌ Sync start failed: ${response.data.message}\n`;
                if (progressFill) progressFill.style.width = '100%';
                if (progressFill) progressFill.style.backgroundColor = '#dc3545';
                if (progressText) progressText.textContent = 'Failed to start';
                throw new Error(response.data.message || 'Failed to start sync');
            }
        } catch (error) {
            console.error(`❌ [ERROR] EVE Observer: Sync start error for ${section}:`, error);
            console.log('🔄 [STEP 27] Showing error notification...');

            // Handle the case where a sync is already running
            if (error.message && error.message.includes('sync is already running')) {
                console.log('🔄 [STEP 28] Sync already running - showing stop option...');

                // Try to extract current status from the error data
                let currentStatus = null;
                if (error.data && error.data.current_status) {
                    currentStatus = error.data.current_status;
                    console.log('🔄 [STEP 29] Extracted current status from error data:', currentStatus);
                } else {
                    // Fallback: try to check status via AJAX
                    console.log('🔄 [STEP 30] Checking sync status via AJAX...');
                    currentStatus = await this.checkSyncStatus();
                }

                if (currentStatus && currentStatus.running) {
                    console.log('🔄 [STEP 31] Showing sync status display...');
                    this.updateSyncStatusDisplay(currentStatus);
                    this.showNotification('A sync is already running. Use the stop button to cancel it first.', 'error');
                } else {
                    this.showNotification(`Failed to start sync ${section}: ${error.message}`, 'error');
                }
            } else {
                this.showNotification(`Failed to start sync ${section}: ${error.message}`, 'error');
            }

            if (progressContent) progressContent.textContent += `❌ Error: ${error.message}\n`;
            if (progressFill) progressFill.style.width = '100%';
            if (progressFill) progressFill.style.backgroundColor = '#dc3545';
            if (progressText) progressText.textContent = 'Error occurred';

            // Restore button state on error
            if (button) {
                button.disabled = false;
                button.innerHTML = originalText;
            }
        }
    }

    startProgressMonitoring(section, progressFill, progressText, progressContent, button, originalText) {
        console.log('🔄 [MONITOR] Starting progress monitoring...');

        let monitoringInterval = setInterval(async () => {
            try {
                const status = await this.checkSyncStatus();
                console.log('🔄 [MONITOR] Current status:', status);

                if (status.running) {
                    // Update progress display
                    const progressPercent = Math.max(10, Math.min(90, status.progress || 10));
                    if (progressFill) progressFill.style.width = `${progressPercent}%`;
                    if (progressText) progressText.textContent = status.message || 'Processing...';

                    // Fetch and display recent log entries
                    try {
                        const recentLogs = await this.getLogs('', [], 30); // Get last 30 log entries
                        if (recentLogs && recentLogs.length > 0) {
                            const logText = recentLogs.map(log => {
                                const timestamp = new Date(log.timestamp).toLocaleString();
                                return `${timestamp} - ${log.level} - ${log.message}`;
                            }).join('\n');
                            if (progressContent) progressContent.textContent = `Sync running: ${status.message || 'Processing...'}\nSection: ${status.section || section}\nProgress: ${progressPercent.toFixed(1)}%\n\nRecent Log Entries:\n${logText}`;
                        } else {
                            if (progressContent) progressContent.textContent = `Sync running: ${status.message || 'Processing...'}\nSection: ${status.section || section}\nProgress: ${progressPercent.toFixed(1)}%\n\nNo recent log entries found.`;
                        }
                    } catch (logError) {
                        console.error('❌ [MONITOR] Error fetching logs:', logError);
                        if (progressContent) progressContent.textContent = `Sync running: ${status.message || 'Processing...'}\nSection: ${status.section || section}\nProgress: ${progressPercent.toFixed(1)}%\n\nError loading logs: ${logError.message}`;
                    }
                } else {
                    // Sync completed or stopped
                    clearInterval(monitoringInterval);
                    console.log('🔄 [MONITOR] Sync completed or stopped');

                    if (status.progress >= 100) {
                        // Success
                        if (progressFill) progressFill.style.width = '100%';
                        if (progressFill) progressFill.style.backgroundColor = '#28a745';
                        if (progressText) progressText.textContent = 'Completed!';

                        // Show final log entries
                        try {
                            const finalLogs = await this.getLogs('', [], 50); // Get last 50 log entries for completion
                            if (finalLogs && finalLogs.length > 0) {
                                const logText = finalLogs.map(log => {
                                    const timestamp = new Date(log.timestamp).toLocaleString();
                                    return `${timestamp} - ${log.level} - ${log.message}`;
                                }).join('\n');
                                if (progressContent) progressContent.textContent = `✅ Sync completed successfully!\n\nFinal Log Entries:\n${logText}`;
                            } else {
                                if (progressContent) progressContent.textContent = `✅ Sync completed successfully!\n\nNo log entries found.`;
                            }
                        } catch (logError) {
                            console.error('❌ [MONITOR] Error fetching final logs:', logError);
                            if (progressContent) progressContent.textContent = `✅ Sync completed successfully!\n\nError loading final logs: ${logError.message}`;
                        }

                        // Reload data after successful sync
                        console.log(`🔄 [MONITOR] Reloading data after successful sync of ${section}`);
                        await this.loadAllData();
                        this.renderAllTables();
                        this.renderChart();

                        this.showNotification(`Successfully synced ${section}`, 'success');
                    } else {
                        // Error or stopped
                        if (progressFill) progressFill.style.width = '100%';
                        if (progressFill) progressFill.style.backgroundColor = '#dc3545';
                        if (progressText) progressText.textContent = 'Failed or stopped';

                        // Show error logs
                        try {
                            const errorLogs = await this.getLogs('', ['ERROR', 'WARNING'], 30); // Get recent error/warning logs
                            if (errorLogs && errorLogs.length > 0) {
                                const logText = errorLogs.map(log => {
                                    const timestamp = new Date(log.timestamp).toLocaleString();
                                    return `${timestamp} - ${log.level} - ${log.message}`;
                                }).join('\n');
                                if (progressContent) progressContent.textContent = `❌ Sync ended unexpectedly\n\nRecent Error/Warning Logs:\n${logText}`;
                            } else {
                                if (progressContent) progressContent.textContent = `❌ Sync ended unexpectedly\n\nNo error logs found.`;
                            }
                        } catch (logError) {
                            console.error('❌ [MONITOR] Error fetching error logs:', logError);
                            if (progressContent) progressContent.textContent = `❌ Sync ended unexpectedly\n\nError loading logs: ${logError.message}`;
                        }

                        this.showNotification(`Sync ${section} ended unexpectedly`, 'error');
                    }

                    // Restore button state
                    if (button) {
                        button.disabled = false;
                        button.innerHTML = originalText;
                    }

                    // Don't hide progress automatically - let user close it manually
                    // setTimeout(() => {
                    //     document.getElementById('sync-progress').style.display = 'none';
                    // }, 5000);
                }
            } catch (error) {
                console.error('❌ [MONITOR] Error checking status:', error);
                clearInterval(monitoringInterval);

                if (progressFill) progressFill.style.width = '100%';
                if (progressFill) progressFill.style.backgroundColor = '#dc3545';
                if (progressText) progressText.textContent = 'Monitoring failed';

                // Show error logs on monitoring failure
                try {
                    const errorLogs = await this.getLogs('', ['ERROR'], 20);
                    if (errorLogs && errorLogs.length > 0) {
                        const logText = errorLogs.map(log => {
                            const timestamp = new Date(log.timestamp).toLocaleString();
                            return `${timestamp} - ${log.level} - ${log.message}`;
                        }).join('\n');
                        if (progressContent) progressContent.textContent = `❌ Error monitoring progress: ${error.message}\n\nRecent Error Logs:\n${logText}`;
                    } else {
                        if (progressContent) progressContent.textContent = `❌ Error monitoring progress: ${error.message}\n\nNo recent error logs found.`;
                    }
                } catch (logError) {
                    console.error('❌ [MONITOR] Error fetching error logs on monitoring failure:', logError);
                    if (progressContent) progressContent.textContent = `❌ Error monitoring progress: ${error.message}\n\nError loading error logs: ${logError.message}`;
                }

                if (button) {
                    button.disabled = false;
                    button.innerHTML = originalText;
                }
            }
        }, 2000); // Check every 2 seconds

        // Stop monitoring after 30 minutes (safety timeout)
        setTimeout(async () => {
            clearInterval(monitoringInterval);
            console.log('🔄 [MONITOR] Monitoring timeout reached');

            if (progressFill) progressFill.style.width = '100%';
            if (progressFill) progressFill.style.backgroundColor = '#dc3545';
            if (progressText) progressText.textContent = 'Timeout reached';

            // Show timeout logs
            try {
                const timeoutLogs = await this.getLogs('', [], 20);
                if (timeoutLogs && timeoutLogs.length > 0) {
                    const logText = timeoutLogs.map(log => {
                        const timestamp = new Date(log.timestamp).toLocaleString();
                        return `${timestamp} - ${log.level} - ${log.message}`;
                    }).join('\n');
                    if (progressContent) progressContent.textContent = `⏰ Monitoring timeout reached (30 minutes)\n\nLast Log Entries:\n${logText}`;
                } else {
                    if (progressContent) progressContent.textContent = `⏰ Monitoring timeout reached (30 minutes)\n\nNo recent log entries found.`;
                }
            } catch (logError) {
                console.error('❌ [MONITOR] Error fetching timeout logs:', logError);
                if (progressContent) progressContent.textContent = `⏰ Monitoring timeout reached (30 minutes)\n\nError loading logs: ${logError.message}`;
            }

            if (button) {
                button.disabled = false;
                button.innerHTML = originalText;
            }
        }, 30 * 60 * 1000); // 30 minutes
    }

    animateProgress(progressFill, progressText, message) {
        // Simulate progress animation
        const steps = [10, 25, 50, 75, 90];
        let currentStep = 0;

        const animate = () => {
            if (currentStep < steps.length) {
                progressFill.style.width = `${steps[currentStep]}%`;
                progressText.textContent = message;
                currentStep++;
                setTimeout(animate, 200);
            }
        };

        animate();
    }

    makeAjaxRequest(data) {
        return new Promise((resolve, reject) => {
            console.log('🔄 [AJAX STEP 1] makeAjaxRequest called with data:', data);
            console.log('🔄 [AJAX STEP 2] Checking jQuery availability:', typeof jQuery !== 'undefined');

            if (typeof jQuery === 'undefined') {
                console.error('❌ [AJAX ERROR] jQuery is not available!');
                reject(new Error('jQuery is not available'));
                return;
            }

            console.log('🔄 [AJAX STEP 3] eveObserverApi.ajaxUrl:', eveObserverApi.ajaxUrl);
            console.log('🔄 [AJAX STEP 4] Preparing jQuery.ajax call...');

            jQuery.ajax({
                url: eveObserverApi.ajaxUrl,
                type: 'POST',
                data: data,
                timeout: 300000, // 5 minute timeout (increased from 60 seconds)
                beforeSend: function(xhr) {
                    console.log('🔄 [AJAX STEP 5] AJAX request about to be sent...');
                    console.log('🔄 [AJAX STEP 6] Request URL:', eveObserverApi.ajaxUrl);
                    console.log('🔄 [AJAX STEP 7] Request data:', data);
                },
                success: (response, textStatus, xhr) => {
                    console.log('✅ [AJAX STEP 8] AJAX request successful');
                    console.log('🔄 [AJAX STEP 9] Response status:', xhr.status);
                    console.log('🔄 [AJAX STEP 10] Response headers:', xhr.getAllResponseHeaders());
                    console.log('🔄 [AJAX STEP 11] Full response:', response);
                    console.log('🔄 [AJAX STEP 12] Response success property:', response.success);
                    resolve(response);
                },
                error: (xhr, status, error) => {
                    console.error('❌ [AJAX STEP 13] AJAX request failed');
                    console.error('🔄 [AJAX STEP 14] XHR object:', xhr);
                    console.error('🔄 [AJAX STEP 15] Status:', status);
                    console.error('🔄 [AJAX STEP 16] Error:', error);
                    console.error('🔄 [AJAX STEP 17] Response text:', xhr.responseText);
                    console.error('🔄 [AJAX STEP 18] Response status:', xhr.status);
                    console.error('🔄 [AJAX STEP 19] Response headers:', xhr.getAllResponseHeaders());

                    let errorMessage = 'Unknown AJAX error';
                    let errorData = null;
                    if (xhr.responseJSON && xhr.responseJSON.data) {
                        errorData = xhr.responseJSON.data;
                        errorMessage = xhr.responseJSON.data.message || errorMessage;
                        console.error('🔄 [AJAX STEP 20] Error from responseJSON.data.message:', errorMessage);
                        console.error('🔄 [AJAX STEP 21] Full error data:', errorData);
                    } else if (xhr.responseText) {
                        errorMessage = xhr.responseText;
                        console.error('🔄 [AJAX STEP 22] Error from responseText:', errorMessage);
                    } else if (error) {
                        errorMessage = error;
                        console.error('🔄 [AJAX STEP 23] Error from error parameter:', errorMessage);
                    }

                    // Create an error object that includes both message and full data
                    const ajaxError = new Error(errorMessage);
                    ajaxError.data = errorData;
                    ajaxError.status = xhr.status;
                    reject(ajaxError);
                }
            });
        });
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `eve-notification eve-notification-${type}`;
        notification.innerHTML = `
            <span class="dashicons ${type === 'success' ? 'dashicons-yes' : 'dashicons-no'}"></span>
            ${message}
        `;

        // Style the notification
        Object.assign(notification.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            background: type === 'success' ? '#28a745' : '#dc3545',
            color: 'white',
            padding: '12px 16px',
            borderRadius: '4px',
            boxShadow: '0 2px 10px rgba(0,0,0,0.2)',
            zIndex: '9999',
            maxWidth: '400px',
            fontWeight: 'bold',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
        });

        document.body.appendChild(notification);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 5000);
    }

    copyOutbidContracts() {
        const outbidContracts = this.data.contracts.filter(contract =>
            contract.meta && contract.meta._eve_contract_outbid === '1'
        );
        console.log('outbidContracts found:', outbidContracts.length);

        if (outbidContracts.length === 0) {
            alert('No outbid contracts found.');
            return;
        }

        const links = outbidContracts.map(contract => {
            const contractId = contract.meta._eve_contract_id;
            const regionId = contract.meta._eve_contract_region_id;
            const title = contract.title?.rendered || `Contract ${contractId}`;

            console.log('Contract:', contractId, 'Region:', regionId, 'Title:', title);

            if (regionId && contractId) {
                return `<font size="14" color="#bfffffff"></font><font size="14" color="#ffd98d00"><a href="contract:${regionId}//${contractId}">[Contract ${contractId}]</a></font>`;
            }
            return '';
        }).filter(link => link);

        const fullText = links.join('\n');
        console.log('Copying text length:', fullText.length);
        copyToClipboard(fullText);
    }

    debouncedSearch(section, query) {
        clearTimeout(this.searchTimeouts[section]);
        this.searchTimeouts[section] = setTimeout(() => {
            this.filterData(section, query);
            this.renderTable(section);
        }, 300);
    }

    filterData(section, query) {
        if (!query.trim()) {
            this.filteredData[section] = [...this.data[section]];
            return;
        }

        const lowercaseQuery = query.toLowerCase();
        this.filteredData[section] = this.data[section].filter(item => {
            const searchableFields = this.getSearchableFields(section);
            return searchableFields.some(field => {
                const value = this.getNestedValue(item, field);
                return value && value.toString().toLowerCase().includes(lowercaseQuery);
            });
        });
    }

    getSearchableFields(section) {
        const fields = {
            characters: ['title.rendered', 'meta._eve_corporation_name', 'meta._eve_alliance_name'],
            blueprints: ['title.rendered', 'meta._eve_bp_type_id', 'meta._eve_bp_location_name'],
            planets: ['title.rendered', 'meta._eve_planet_type', 'meta._eve_planet_solar_system_name'],
            corporations: ['title.rendered', 'meta._eve_corp_ticker', 'meta._eve_corp_name'],
            contracts: ['title.rendered', 'meta._eve_contract_type', 'meta._eve_contract_status']
        };
        return fields[section] || [];
    }

    getNestedValue(obj, path) {
        return path.split('.').reduce((current, key) => current?.[key], obj);
    }

    renderChart() {
        let canvas = document.getElementById('eveChart');
        if (!canvas) {
            console.log('⚠️ [CHART] Canvas element not found, skipping chart creation');
            return;
        }

        // Check if Chart.js is available
        if (typeof Chart === 'undefined') {
            console.error('❌ [CHART] Chart.js is not loaded! Skipping chart creation.');
            console.log('🔄 [CHART] Chart object:', typeof Chart);
            console.log('🔄 [CHART] This may prevent sync functionality from working properly.');
            return;
        }

        // Destroy any existing chart on the current canvas before replacing
        const existingChart = Chart.getChart(canvas);
        if (existingChart) {
            console.log('🔄 [CHART] Destroying existing chart before replacement...');
            existingChart.destroy();
        }

        // Replace the canvas with a fresh one to avoid Chart.js conflicts
        const parent = canvas.parentElement;
        if (parent) {
            console.log('🔄 [CHART] Replacing canvas with fresh one...');
            const newCanvas = document.createElement('canvas');
            newCanvas.id = 'eveChart';
            newCanvas.className = canvas.className;
            newCanvas.style.cssText = canvas.style.cssText;
            parent.replaceChild(newCanvas, canvas);
            canvas = newCanvas;
        }

        // Set canvas dimensions
        const computedStyle = getComputedStyle(canvas.parentElement);
        const width = parseInt(computedStyle.width);
        const height = parseInt(computedStyle.height);
        if (width && height) {
            canvas.width = width;
            canvas.height = height;
        }

        const counts = {
            Characters: this.data.characters.length,
            Blueprints: this.data.blueprints.length,
            Planets: this.data.planets.length,
            Corporations: this.data.corporations.length,
            Contracts: this.data.contracts.length
        };

        // Calculate percentages for better visualization
        const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
        const percentages = Object.fromEntries(
            Object.entries(counts).map(([key, value]) => [key, total > 0 ? (value / total * 100) : 0])
        );

        console.log('🔄 [CHART] Creating new chart with data:', counts);
        try {
            this.chart = new Chart(canvas.getContext('2d'), {
                id: `eve-chart-${Date.now()}`, // Unique ID to prevent conflicts
                type: 'doughnut',
                data: {
                    labels: Object.keys(counts).map(key => `${key} (${counts[key]})`),
                    datasets: [{
                        data: Object.values(counts),
                        backgroundColor: [
                            'rgba(0, 122, 255, 0.8)',
                            'rgba(255, 149, 0, 0.8)',
                            'rgba(52, 199, 89, 0.8)',
                            'rgba(255, 59, 48, 0.8)',
                            'rgba(142, 142, 147, 0.8)'
                        ],
                        borderColor: [
                            'rgba(0, 122, 255, 1)',
                            'rgba(255, 149, 0, 1)',
                            'rgba(52, 199, 89, 1)',
                            'rgba(255, 59, 48, 1)',
                            'rgba(142, 142, 147, 1)'
                        ],
                        borderWidth: 2,
                        hoverOffset: 8,
                        hoverBorderWidth: 3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                padding: 20,
                                usePointStyle: true,
                                font: {
                                    size: 12,
                                    family: '-apple-system, BlinkMacSystemFont, sans-serif'
                                }
                            }
                        },
                        tooltip: {
                            backgroundColor: 'rgba(0, 0, 0, 0.8)',
                            titleColor: '#fff',
                            bodyColor: '#fff',
                            callbacks: {
                                label: (context) => {
                                    const label = context.label.split(' (')[0];
                                    const count = context.parsed;
                                    const percentage = percentages[label];
                                    return `${label}: ${count} (${percentage.toFixed(1)}%)`;
                                }
                            }
                        }
                    },
                    animation: {
                        animateScale: true,
                        animateRotate: true,
                        duration: 1000,
                        easing: 'easeInOutQuart'
                    },
                    onClick: (event, elements) => {
                        if (elements.length > 0) {
                            const element = elements[0];
                            const label = this.chart.data.labels[element.index].split(' (')[0].toLowerCase();
                            this.scrollToSection(label + 's');
                        }
                    }
                }
            });
            console.log('✅ [CHART] Chart created successfully');
        } catch (error) {
            console.error('❌ [CHART] Error creating chart:', error);
            console.log('🔄 [CHART] Chart creation failed, but continuing with dashboard initialization');
            // Don't throw error - allow dashboard to continue working without chart
        }
    }

    scrollToSection(sectionId) {
        const section = document.getElementById(sectionId + '-section');
        if (section) {
            section.scrollIntoView({ behavior: 'smooth', block: 'start' });
            // Add temporary highlight
            section.style.transition = 'background-color 0.3s';
            section.style.backgroundColor = 'rgba(0, 122, 255, 0.05)';
            setTimeout(() => {
                section.style.backgroundColor = '';
            }, 1000);
        }
    }

    renderAllTables() {
        ['characters', 'blueprints', 'planets', 'corporations', 'contracts'].forEach(section => {
            this.renderTable(section);
        });
    }

    renderTable(section) {
        const tbody = document.getElementById(`${section}-tbody`);
        if (!tbody) return;

        const data = this.filteredData[section] || [];
        tbody.innerHTML = '';

        if (data.length === 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td colspan="${this.getTableColumns(section)}" style="text-align: center; padding: 40px; color: var(--text-secondary);">No ${section} found</td>`;
            tbody.appendChild(tr);
            return;
        }

        data.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = this.getTableRowHTML(section, item);
            tbody.appendChild(tr);
        });

        // Update pagination if needed
        if (['blueprints', 'planets'].includes(section)) {
            this.renderPagination(section);
        }
    }

    getTableColumns(section) {
        const columns = {
            characters: 5,
            blueprints: 6,
            planets: 5,
            corporations: 5,
            contracts: 6
        };
        return columns[section] || 1;
    }

    getTableRowHTML(section, item) {
        switch (section) {
            case 'characters':
                return `
                    <td>${this.decodeHtml(item.title?.rendered || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_corporation_name || item.meta?._eve_corporation_id || 'N/A')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_alliance_name || item.meta?._eve_alliance_id || 'N/A')}</td>
                    <td>${this.formatSecurityStatus(item.meta?._eve_security_status)}</td>
                    <td>${this.escapeHtml(item.meta?._eve_location_name || 'Unknown')}</td>
                `;

            case 'blueprints':
                return `
                    <td>${this.decodeHtml(item.title?.rendered || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_bp_type_id || 'N/A')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_bp_location_name || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_bp_me || 'N/A')}%</td>
                    <td>${this.escapeHtml(item.meta?._eve_bp_te || 'N/A')}%</td>
                    <td>${this.escapeHtml(item.meta?._eve_bp_runs || 'N/A')}</td>
                `;

            case 'planets':
                const pinsCount = this.getPinsCount(item.meta?._eve_planet_pins_data);
                return `
                    <td>${this.decodeHtml(item.title?.rendered || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_planet_type || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_planet_upgrade_level || 'N/A')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_planet_solar_system_name || 'Unknown')}</td>
                    <td>${pinsCount}</td>
                `;

            case 'corporations':
                return `
                    <td>${this.decodeHtml(item.title?.rendered || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_corp_ticker || 'N/A')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_corp_member_count || 'N/A')}</td>
                    <td>${this.formatNumber(item.meta?._eve_corp_tax_rate)}%</td>
                    <td>${this.formatISK(item.meta?._eve_corp_wallet_balance)}</td>
                `;

            case 'contracts':
                const isOutbid = item.meta?._eve_contract_outbid === '1';
                const statusClass = isOutbid ? 'eve-status-error' : 'eve-status-ok';
                const statusText = isOutbid ? '' : '';
                const statusIcon = isOutbid ? '⚠️' : '✅';

                return `
                    <td>${this.decodeHtml(item.title?.rendered || 'Unknown')}</td>
                    <td>${this.formatContractType(item.meta?._eve_contract_type)}</td>
                    <td>${this.formatContractStatus(item.meta?._eve_contract_status)}</td>
                    <td>${this.formatISK(item.meta?._eve_contract_price)}</td>
                    <td>${this.formatISK(item.meta?._eve_contract_competing_price) || 'N/A'}</td>
                    <td><span class="eve-status-indicator ${statusClass}">${statusIcon} ${statusText}</span></td>
                `;

            default:
                return '<td colspan="1">Unknown section</td>';
        }
    }

    formatSecurityStatus(status) {
        if (!status || status === 'N/A') return 'N/A';
        const num = parseFloat(status);
        return num.toFixed(2);
    }

    getPinsCount(pinsData) {
        if (!pinsData) return '0';
        try {
            const pins = JSON.parse(pinsData);
            return pins.length || 0;
        } catch {
            return '0';
        }
    }

    formatNumber(num) {
        if (!num && num !== 0) return 'N/A';
        return parseFloat(num).toFixed(2);
    }

    formatISK(amount) {
        if (!amount && amount !== 0) return 'N/A';
        const num = parseFloat(amount);
        if (num >= 1000000000) {
            return (num / 1000000000).toFixed(2) + 'B ISK';
        } else if (num >= 1000000) {
            return (num / 1000000).toFixed(2) + 'M ISK';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(2) + 'K ISK';
        }
        return num.toFixed(2) + ' ISK';
    }

    formatContractType(type) {
        if (!type) return 'Unknown';
        return type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    formatContractStatus(status) {
        if (!status) return 'Unknown';
        return status.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    renderPagination(section) {
        const paginationEl = document.getElementById(`${section}-pagination`);
        if (!paginationEl) return;

        const totalItems = this.data[section].length;
        const totalPages = Math.ceil(totalItems / this.itemsPerPage);
        const currentPage = this.currentPage[section];

        if (totalPages <= 1) {
            paginationEl.innerHTML = '';
            return;
        }

        paginationEl.innerHTML = `
            <button id="prev-${section}" ${currentPage === 1 ? 'disabled' : ''}>Previous</button>
            <span>Page ${currentPage} of ${totalPages}</span>
            <button id="next-${section}" ${currentPage === totalPages ? 'disabled' : ''}>Next</button>
        `;

        // Add event listeners
        const prevBtn = document.getElementById(`prev-${section}`);
        const nextBtn = document.getElementById(`next-${section}`);

        prevBtn?.addEventListener('click', () => this.changePage(section, currentPage - 1));
        nextBtn?.addEventListener('click', () => this.changePage(section, currentPage + 1));
    }

    async changePage(section, newPage) {
        if (newPage < 1) return;

        this.currentPage[section] = newPage;

        // Reload data for this section
        try {
            const url = `/wp-json/wp/v2/${this.postTypeMap[section]}?per_page=${this.itemsPerPage}&page=${newPage}&_embed`;
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();

            this.data[section] = Array.isArray(data) ? data : [];
            this.filteredData[section] = [...this.data[section]];
            this.renderTable(section);
        } catch (error) {
            console.error(`Error loading ${section} page ${newPage}:`, error);
        }
    }

    hideLoaders() {
        const sections = ['characters', 'blueprints', 'planets', 'corporations', 'contracts'];
        sections.forEach(section => {
            const loader = document.getElementById(`${section}-loading`);
            const content = document.getElementById(`${section}-content`);
            if (loader) loader.style.display = 'none';
            if (content) content.style.display = 'block';
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    decodeHtml(text) {
        if (!text) return text;

        const temp = document.createElement('div');
        temp.innerHTML = text;
        const decoded = temp.textContent || temp.innerText || text;

        // Replace en dash with hyphen
        return decoded.replace(/–/g, '-');
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM content loaded, initializing EVE Dashboard');
    new EVEDashboard();
});
