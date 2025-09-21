// EVE Observer Dashboard JavaScript
document.addEventListener('DOMContentLoaded', function() {
    loadPIDashboard();
});

function loadPIDashboard() {
    fetch('/wp-json/wp/v2/eve_planet')
        .then(response => response.json())
        .then(planets => {
            displayPIDashboard(planets);
        })
        .catch(error => {
            console.error('Error loading planet data:', error);
            document.getElementById('eveChart').innerHTML = '<p>Error loading PI data.</p>';
        });
}

function displayPIDashboard(planets) {
    const container = document.getElementById('eveChart');
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