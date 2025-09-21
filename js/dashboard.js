// EVE Observer Dashboard JavaScript
document.addEventListener('DOMContentLoaded', function() {
    loadDashboardData();
});

// Global variables for pagination
let currentPage = {
    blueprints: 1,
    planets: 1
};
const itemsPerPage = 10;
let isInitialLoad = true;

function loadDashboardData() {
    Promise.all([
        fetch('/wp-json/wp/v2/eve_character?per_page=100').then(r => r.json()),
        fetch(`/wp-json/wp/v2/eve_blueprint?per_page=${itemsPerPage}&page=${currentPage.blueprints}`).then(r => r.json()),
        fetch(`/wp-json/wp/v2/eve_planet?per_page=${itemsPerPage}&page=${currentPage.planets}`).then(r => r.json())
    ]).then(([characters, blueprints, planets]) => {
        if (isInitialLoad) {
            displayChart(characters.length, blueprints.length, planets.length);
            isInitialLoad = false;
        }
        loadPIDashboard(planets);
        loadBlueprintDashboard(blueprints);
    }).catch(error => {
        console.error('Error loading data:', error);
    });
}

function loadBlueprintDashboard(blueprints) {
    let container = document.getElementById('blueprint-dashboard');
    if (!container) {
        container = document.createElement('div');
        container.id = 'blueprint-dashboard';
        document.querySelector('.wrap').appendChild(container);
    }
    container.innerHTML = '<h3>Blueprint Dashboard</h3>';

    if (blueprints.length === 0) {
        container.innerHTML += '<p>No blueprint data available.</p>';
        return;
    }

    // Create blueprint list
    const blueprintList = document.createElement('div');
    blueprintList.id = 'blueprint-list';

    blueprints.forEach(blueprint => {
        const bpDiv = document.createElement('div');
        bpDiv.className = 'blueprint-item';
        bpDiv.innerHTML = `<h4>${blueprint.title.rendered}</h4>
                           <p>Type ID: ${blueprint.meta._eve_blueprint_type_id || 'Unknown'}</p>
                           <p>Location: ${blueprint.meta._eve_blueprint_location || 'Unknown'}</p>
                           <p>Material Efficiency: ${blueprint.meta._eve_blueprint_me || 'N/A'}%</p>
                           <p>Time Efficiency: ${blueprint.meta._eve_blueprint_te || 'N/A'}%</p>`;
        blueprintList.appendChild(bpDiv);
    });

    container.appendChild(blueprintList);

    // Add pagination controls
    const paginationControls = createPaginationControls('blueprints', blueprints.length === itemsPerPage);
    container.appendChild(paginationControls);
}

function loadPIDashboard(planets) {
    let container = document.getElementById('pi-dashboard');
    if (!container) {
        container = document.createElement('div');
        container.id = 'pi-dashboard';
        document.querySelector('.wrap').appendChild(container);
    }
    container.innerHTML = '<h3>Planet Interaction Dashboard</h3>';

    if (planets.length === 0) {
        container.innerHTML += '<p>No planet data available.</p>';
        return;
    }

    planets.forEach(planet => {
        const planetDiv = document.createElement('div');
        planetDiv.className = 'planet-item';
        planetDiv.innerHTML = `<h4>${planet.title.rendered}</h4>
                               <p>Type: ${planet.meta._eve_planet_type || 'Unknown'}</p>
                               <p>Upgrade Level: ${planet.meta._eve_planet_upgrade_level || 'N/A'}</p>`;

        const pinsData = planet.meta._eve_planet_pins_data;
        if (pinsData) {
            try {
                const pins = JSON.parse(pinsData);
                if (pins.length > 0) {
                    const pinsList = document.createElement('ul');
                    pins.forEach(pin => {
                        const li = document.createElement('li');
                        li.innerHTML = `Pin ${pin.pin_id} (Type: ${pin.type_id}) - Expires: <span id="timer-${pin.pin_id}"></span>`;
                        pinsList.appendChild(li);
                        startTimer(pin.expiry_time, `timer-${pin.pin_id}`);
                    });
                    planetDiv.appendChild(pinsList);
                } else {
                    planetDiv.innerHTML += '<p>No active pins.</p>';
                }
            } catch (e) {
                planetDiv.innerHTML += '<p>Error parsing pins data.</p>';
            }
        } else {
            planetDiv.innerHTML += '<p>No pins data.</p>';
        }

        container.appendChild(planetDiv);
    });

    // Add pagination controls
    const paginationControls = createPaginationControls('planets', planets.length === itemsPerPage);
    container.appendChild(paginationControls);
}

function startTimer(expiryTime, elementId) {
    const expiry = new Date(expiryTime);
    const timerElement = document.getElementById(elementId);

    function updateTimer() {
        const now = new Date();
        const diff = expiry - now;

        if (diff <= 0) {
            timerElement.textContent = 'Expired';
            return;
        }

        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((diff % (1000 * 60)) / 1000);

        timerElement.textContent = `${days}d ${hours}h ${minutes}m ${seconds}s`;
    }

    updateTimer();
    setInterval(updateTimer, 1000);
}

function createPaginationControls(dataType, hasNextPage) {
    const controls = document.createElement('div');
    controls.className = 'pagination-controls';
    controls.innerHTML = `
        <button id="prev-${dataType}" ${currentPage[dataType] === 1 ? 'disabled' : ''}>Previous</button>
        <span>Page ${currentPage[dataType]}</span>
        <button id="next-${dataType}" ${!hasNextPage ? 'disabled' : ''}>Next</button>
    `;

    // Add event listeners
    controls.querySelector(`#prev-${dataType}`).addEventListener('click', () => {
        if (currentPage[dataType] > 1) {
            currentPage[dataType]--;
            loadDashboardData();
        }
    });

    controls.querySelector(`#next-${dataType}`).addEventListener('click', () => {
        if (hasNextPage) {
            currentPage[dataType]++;
            loadDashboardData();
        }
    });

    return controls;
}