// EVE Observer Dashboard JavaScript
document.addEventListener('DOMContentLoaded', function() {
    loadDashboardData();
});

function loadDashboardData() {
    Promise.all([
        fetch('/wp-json/wp/v2/eve_character').then(r => r.json()),
        fetch('/wp-json/wp/v2/eve_blueprint').then(r => r.json()),
        fetch('/wp-json/wp/v2/eve_planet').then(r => r.json())
    ]).then(([characters, blueprints, planets]) => {
        displayChart(characters.length, blueprints.length, planets.length);
        loadPIDashboard(planets);
    }).catch(error => {
        console.error('Error loading data:', error);
    });
}

function displayChart(charCount, bpCount, planetCount) {
    const ctx = document.getElementById('eveChart').getContext('2d');
    const eveChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Characters', 'Blueprints', 'Planets'],
            datasets: [{
                label: 'Count',
                data: [charCount, bpCount, planetCount],
                backgroundColor: [
                    'rgba(255, 99, 132, 0.2)',
                    'rgba(54, 162, 235, 0.2)',
                    'rgba(255, 206, 86, 0.2)'
                ],
                borderColor: [
                    'rgba(255, 99, 132, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

function loadPIDashboard(planets) {
    const container = document.createElement('div');
    container.id = 'pi-dashboard';
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

    document.querySelector('.wrap').appendChild(container);
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