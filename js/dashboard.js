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
        this.postTypeMap = {
            characters: 'eve_character',
            blueprints: 'eve_blueprint',
            planets: 'eve_planet',
            corporations: 'eve_corporation',
            contracts: 'eve_contract'
        };

        this.init();
    }

    async init() {
        console.log('🔄 [INIT] EVEDashboard init called');
        console.log('🔄 [INIT] DOM ready state:', document.readyState);
        try {
            console.log('🔄 [INIT] Starting loadAllData()...');
            await this.loadAllData();
            console.log('✅ [INIT] loadAllData() completed');

            console.log('🔄 [INIT] Starting setupSearch()...');
            this.setupSearch();
            console.log('✅ [INIT] setupSearch() completed');

            console.log('🔄 [INIT] Starting setupCardClicks()...');
            this.setupCardClicks();
            console.log('✅ [INIT] setupCardClicks() completed');

            console.log('🔄 [INIT] Starting renderChart()...');
            this.renderChart();
            console.log('✅ [INIT] renderChart() completed');

            console.log('🔄 [INIT] Starting renderAllTables()...');
            this.renderAllTables();
            console.log('✅ [INIT] renderAllTables() completed');

            console.log('🔄 [INIT] Starting setupActionButtons()...');
            this.setupActionButtons();
            console.log('✅ [INIT] setupActionButtons() completed');

            console.log('🔄 [INIT] Starting hideLoaders()...');
            this.hideLoaders();
            console.log('✅ [INIT] hideLoaders() completed');

            console.log('🎉 [INIT] Dashboard initialization completed successfully!');
        } catch (error) {
            console.error('❌ [INIT ERROR] Dashboard initialization failed:', error);
        }
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
            console.log('🔄 [INIT STEP 9] eveObserverApi.restUrl:', eveObserverApi.restUrl);
        } else {
            console.error('❌ [INIT ERROR] eveObserverApi is not defined! This will prevent sync from working.');
        }

        console.log('🔄 [INIT STEP 10] Setting up individual sync button event listeners...');
        syncButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const section = button.getAttribute('data-section');
                console.log('🔄 [INDIVIDUAL SYNC] Sync button clicked for section:', section);
                this.syncSection(section, button);
            });
        });
        console.log('✅ [INIT STEP 11] Individual sync button listeners set up');

        console.log('🔄 [INIT STEP 12] Setting up sync all button event listener...');
        if (syncAllButton) {
            syncAllButton.addEventListener('click', (e) => {
                console.log('🔄 [STEP 1] Sync All button clicked - event detected!');
                console.log('🔄 [STEP 2] Event object:', e);
                console.log('🔄 [STEP 3] Button element:', syncAllButton);
                alert('Sync All button clicked! Check console for details.');
                console.log('🔄 [STEP 4] Alert dismissed, proceeding with sync...');
                this.syncSection('all', syncAllButton);
            });
            console.log('✅ [INIT STEP 13] Sync all button event listener set up');
        } else {
            console.error('❌ [INIT ERROR] Sync all button not found!');
        }
    }

    async syncSection(section, button) {
        console.log(`🔄 [STEP 5] EVE Observer: Starting sync for section: ${section}`);
        console.log(`🔄 [STEP 6] Button element:`, button);
        console.log(`🔄 [STEP 7] Button original text:`, button.innerHTML);

        console.log('🔄 [STEP 8] Checking eveObserverApi availability...');
        console.log('🔄 [STEP 9] eveObserverApi available at sync time:', typeof eveObserverApi !== 'undefined');

        if (typeof eveObserverApi === 'undefined') {
            console.error('❌ [ERROR] eveObserverApi is not defined!');
            console.log('❌ [STEP 10] Showing error notification...');
            this.showNotification('API configuration error - please refresh the page', 'error');
            return;
        }

        console.log('✅ [STEP 11] eveObserverApi is available');
        console.log('🔄 [STEP 12] API configuration:', {
            nonce: eveObserverApi.nonce ? 'present' : 'missing',
            restUrl: eveObserverApi.restUrl
        });

        // Disable button and show loading state
        console.log('🔄 [STEP 13] Disabling button and setting loading state...');
        const originalText = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="dashicons dashicons-update dashicons-spin"></span> Syncing...';
        console.log('✅ [STEP 14] Button disabled and loading state set');

        try {
            console.log(`🔄 [STEP 15] Preparing API request to sync ${section}`);
            console.log('🔄 [STEP 16] API URL:', eveObserverApi.restUrl + 'sync/' + section);
            console.log('🔄 [STEP 17] Nonce:', eveObserverApi.nonce);

            const requestData = {
                method: 'POST',
                headers: {
                    'X-WP-Nonce': eveObserverApi.nonce,
                    'Content-Type': 'application/json'
                }
            };
            console.log('🔄 [STEP 18] Request configuration:', requestData);

            console.log(`🔄 [STEP 19] Making fetch request to: ${eveObserverApi.restUrl}sync/${section}`);
            const response = await fetch(`${eveObserverApi.restUrl}sync/${section}`, requestData);
            console.log('✅ [STEP 20] Fetch request completed');
            console.log('🔄 [STEP 21] Response status:', response.status);
            console.log('🔄 [STEP 22] Response ok:', response.ok);

            if (!response.ok) {
                console.log('❌ [STEP 23] Response not ok, processing error...');
                const errorData = await response.json().catch(() => ({ message: 'Unknown error' }));
                console.log('🔄 [STEP 24] Error data:', errorData);

                // Check for specific error types
                if (errorData.code === 'function_disabled') {
                    console.log('❌ [STEP 25] Detected shell_exec disabled error');
                    throw new Error(`Server configuration error: ${errorData.message}. Please contact your hosting provider to enable shell_exec function.`);
                }

                console.log('❌ [STEP 26] Generic HTTP error');
                throw new Error(`HTTP ${response.status}: ${errorData.message || response.statusText}`);
            }

            console.log('✅ [STEP 27] Response ok, parsing JSON...');
            const result = await response.json();
            console.log(`✅ [STEP 28] JSON parsed successfully`);
            console.log(`🔄 [STEP 29] EVE Observer: Sync response for ${section}:`, result);

            if (result.success) {
                console.log('✅ [STEP 30] Sync was successful');
                const message = result.execution_time
                    ? `Successfully synced ${section} in ${result.execution_time}s`
                    : `Successfully synced ${section}`;
                console.log('🔄 [STEP 31] Success message:', message);
                console.log('🔄 [STEP 32] Showing success notification...');
                this.showNotification(message, 'success');

                // Reload data after successful sync
                console.log(`🔄 [STEP 33] Reloading data after successful sync of ${section}`);
                console.log('🔄 [STEP 34] Calling loadAllData()...');
                await this.loadAllData();
                console.log('✅ [STEP 35] Data reloaded successfully');
                console.log('🔄 [STEP 36] Calling renderAllTables()...');
                this.renderAllTables();
                console.log('✅ [STEP 37] Tables rendered');
                console.log('🔄 [STEP 38] Calling renderChart()...');
                this.renderChart();
                console.log('✅ [STEP 39] Chart rendered');
            } else {
                console.log('❌ [STEP 40] Sync reported failure in response');
                throw new Error(result.message || 'Sync failed');
            }
        } catch (error) {
            console.error(`❌ [ERROR] EVE Observer: Sync error for ${section}:`, error);
            console.log('🔄 [STEP 41] Showing error notification...');
            this.showNotification(`Failed to sync ${section}: ${error.message}`, 'error');
        } finally {
            // Restore button state
            console.log('🔄 [STEP 42] Restoring button state...');
            button.disabled = false;
            button.innerHTML = originalText;
            console.log('✅ [STEP 43] Button state restored');
            console.log(`🔄 [STEP 44] EVE Observer: Sync operation completed for ${section}`);
        }
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
        console.log('copyOutbidContracts called, contracts count:', this.data.contracts.length);
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
        const ctx = document.getElementById('eveChart');
        if (!ctx) return;

        // Destroy existing chart if it exists
        if (this.chart) {
            console.log('🔄 [CHART] Destroying existing chart...');
            this.chart.destroy();
            this.chart = null;
        }

        // Clear the canvas context
        const canvas = ctx;
        const context = canvas.getContext('2d');
        context.clearRect(0, 0, canvas.width, canvas.height);

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
        this.chart = new Chart(ctx, {
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
