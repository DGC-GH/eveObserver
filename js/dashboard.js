// EVE Observer Dashboard JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Sample data - in real implementation, fetch from WP REST API
    const ctx = document.getElementById('eveChart').getContext('2d');
    const eveChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Characters', 'Blueprints', 'Industry Jobs', 'Planets'],
            datasets: [{
                label: 'Count',
                data: [1, 28, 10, 0], // Sample data
                backgroundColor: [
                    'rgba(255, 99, 132, 0.2)',
                    'rgba(54, 162, 235, 0.2)',
                    'rgba(255, 206, 86, 0.2)',
                    'rgba(75, 192, 192, 0.2)'
                ],
                borderColor: [
                    'rgba(255, 99, 132, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(75, 192, 192, 1)'
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
});