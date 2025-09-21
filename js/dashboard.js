// EVE Observer Dashboard - Modern JavaScript
class EVEDashboard {
    constructor() {
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

        this.init();
    }

    async init() {
        await this.loadAllData();
        this.setupSearch();
        this.setupCardClicks();
        this.setupActionButtons();
        this.renderChart();
        this.renderAllTables();
        this.hideLoaders();
    }

    async loadAllData() {
        const endpoints = [
            { key: 'characters', url: '/wp-json/wp/v2/eve_character?per_page=100&_embed' },
            { key: 'blueprints', url: `/wp-json/wp/v2/eve_blueprint?per_page=${this.itemsPerPage}&page=${this.currentPage.blueprints}&_embed` },
            { key: 'planets', url: `/wp-json/wp/v2/eve_planet?per_page=${this.itemsPerPage}&page=${this.currentPage.planets}&_embed` },
            { key: 'corporations', url: '/wp-json/wp/v2/eve_corporation?per_page=100&_embed' },
            { key: 'contracts', url: '/wp-json/wp/v2/eve_contract?per_page=100&_embed' }
        ];

        const promises = endpoints.map(async ({ key, url }) => {
            try {
                const response = await fetch(url);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                this.data[key] = Array.isArray(data) ? data : [];
            } catch (error) {
                console.error(`Error loading ${key}:`, error);
                this.data[key] = [];
            }
        });

        await Promise.all(promises);
        this.filteredData = { ...this.data };
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
            contracts: ['title', 'type', 'status', 'price', 'issuer', 'outbid']
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
        if (sortKey === 'price' || sortKey === 'balance') {
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
        const copyOutbidBtn = document.getElementById('copy-outbid-contracts');
        if (copyOutbidBtn) {
            copyOutbidBtn.addEventListener('click', () => this.copyOutbidContracts());
        }
    }

    copyOutbidContracts() {
        const outbidContracts = this.data.contracts.filter(contract => 
            contract.meta && contract.meta._eve_contract_outbid === 'true'
        );

        if (outbidContracts.length === 0) {
            alert('No outbid contracts found.');
            return;
        }

        const links = outbidContracts.map(contract => {
            const contractId = contract.meta._eve_contract_id;
            const regionId = contract.meta._eve_contract_region_id || contract.meta._eve_contract_start_location_id;
            const title = contract.title?.rendered || `Contract ${contractId}`;
            
            if (regionId && contractId) {
                return `<a href="contract:${regionId}//${contractId}">${this.escapeHtml(title)}</a>`;
            }
            return '';
        }).filter(link => link);

        const fullText = links.join('\n');
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

        new Chart(ctx, {
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
                    <td>${this.escapeHtml(item.title?.rendered || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_corporation_name || item.meta?._eve_corporation_id || 'N/A')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_alliance_name || item.meta?._eve_alliance_id || 'N/A')}</td>
                    <td>${this.formatSecurityStatus(item.meta?._eve_security_status)}</td>
                    <td>${this.escapeHtml(item.meta?._eve_location_name || 'Unknown')}</td>
                `;

            case 'blueprints':
                return `
                    <td>${this.escapeHtml(item.title?.rendered || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_bp_type_id || 'N/A')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_bp_location_name || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_bp_me || 'N/A')}%</td>
                    <td>${this.escapeHtml(item.meta?._eve_bp_te || 'N/A')}%</td>
                    <td>${this.escapeHtml(item.meta?._eve_bp_runs || 'N/A')}</td>
                `;

            case 'planets':
                const pinsCount = this.getPinsCount(item.meta?._eve_planet_pins_data);
                return `
                    <td>${this.escapeHtml(item.title?.rendered || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_planet_type || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_planet_upgrade_level || 'N/A')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_planet_solar_system_name || 'Unknown')}</td>
                    <td>${pinsCount}</td>
                `;

            case 'corporations':
                return `
                    <td>${this.escapeHtml(item.title?.rendered || 'Unknown')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_corp_ticker || 'N/A')}</td>
                    <td>${this.escapeHtml(item.meta?._eve_corp_member_count || 'N/A')}</td>
                    <td>${this.formatNumber(item.meta?._eve_corp_tax_rate)}%</td>
                    <td>${this.formatISK(item.meta?._eve_corp_wallet_balance)}</td>
                `;

            case 'contracts':
                const isOutbid = item.meta?._eve_contract_outbid === 'true';
                const statusClass = isOutbid ? 'eve-status-error' : 'eve-status-ok';
                const statusText = isOutbid ? 'Outbid' : 'OK';
                const statusIcon = isOutbid ? '⚠️' : '✅';

                return `
                    <td>${this.escapeHtml(item.title?.rendered || 'Unknown')}</td>
                    <td>${this.formatContractType(item.meta?._eve_contract_type)}</td>
                    <td>${this.formatContractStatus(item.meta?._eve_contract_status)}</td>
                    <td>${this.formatISK(item.meta?._eve_contract_price)}</td>
                    <td>${this.escapeHtml(item.meta?._eve_contract_issuer_name || 'Unknown')}</td>
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
            const url = `/wp-json/wp/v2/eve_${section}?per_page=${this.itemsPerPage}&page=${newPage}&_embed`;
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
        ['characters', 'blueprints', 'planets', 'corporations', 'contracts'].forEach(section => {
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
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new EVEDashboard();
});