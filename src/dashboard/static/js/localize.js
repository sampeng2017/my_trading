/**
 * Localize timestamps
 * Converts UTC ISO strings in data-timestamp to local browser time.
 * Usage: <span class="local-time" data-timestamp="2023-01-01T12:00:00Z">...</span>
 */
document.addEventListener('DOMContentLoaded', function () {
    const timeElements = document.querySelectorAll('.local-time');

    timeElements.forEach(el => {
        const isoTime = el.getAttribute('data-timestamp');
        if (!isoTime || isoTime === 'None') return;

        try {
            const date = new Date(isoTime);
            // Check if date is valid
            if (isNaN(date.getTime())) return;

            // Format: "Feb 2, 2026, 3:21:10 PM" (varies by locale)
            el.textContent = date.toLocaleString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                second: '2-digit'
            });

            // Add full date as tooltip
            el.title = date.toString();
        } catch (e) {
            console.error('Date localization failed:', e);
        }
    });
});
