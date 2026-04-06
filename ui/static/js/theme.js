document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('themeToggle');
    const currentTheme = localStorage.getItem('theme');
    const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');

    function applyTheme(theme) {
        if (theme === 'dark') {
            document.body.classList.remove('theme-light');
            document.body.classList.add('theme-dark');
            if (themeToggle) themeToggle.checked = true;
        } else {
            document.body.classList.remove('theme-dark');
            document.body.classList.add('theme-light');
            if (themeToggle) themeToggle.checked = false;
        }
        // Apply theme to navbar as well, if it exists
        const navbar = document.querySelector('.navbar');
        if (navbar) {
            if (theme === 'dark') {
                navbar.classList.remove('theme-light', 'navbar-light', 'bg-light');
                navbar.classList.add('theme-dark', 'navbar-dark', 'bg-dark');
            } else {
                navbar.classList.remove('theme-dark', 'navbar-dark', 'bg-dark');
                navbar.classList.add('theme-light', 'navbar-light', 'bg-light');
            }
        }
    }

    // Apply saved theme or default to system preference or light theme
    if (currentTheme) {
        applyTheme(currentTheme);
    } else if (prefersDarkScheme.matches) {
        applyTheme('dark');
        localStorage.setItem('theme', 'dark'); // Save system preference if no explicit choice yet
    } else {
        applyTheme('light'); // Default to light
    }

    if (themeToggle) {
        themeToggle.addEventListener('change', function() {
            let theme = 'light';
            if (this.checked) {
                theme = 'dark';
            }
            localStorage.setItem('theme', theme);
            applyTheme(theme);
        });
    }

    // Listen for changes in system preference
    prefersDarkScheme.addEventListener('change', (e) => {
        // Only change if no explicit user preference is set
        if (!localStorage.getItem('theme')) {
            if (e.matches) {
                applyTheme('dark');
            } else {
                applyTheme('light');
            }
        }
    });
});
