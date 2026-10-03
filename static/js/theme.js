// Light or dark colours: the system setting, unless the visitor chose with the switch in
// the header. The choice is kept in this browser (localStorage), not on the account.
// Loaded in <head> without defer, so the saved colours apply before the page draws.
(function () {
    var root = document.documentElement;
    var KEY = 'theme';
    var systemDark = window.matchMedia('(prefers-color-scheme: dark)');

    function saved() {
        try {
            var theme = localStorage.getItem(KEY);
            return theme === 'light' || theme === 'dark' ? theme : null;
        } catch (error) {
            // Storage blocked (private window, site data off): follow the system
            return null;
        }
    }

    function current() {
        return root.dataset.theme || (systemDark.matches ? 'dark' : 'light');
    }

    var theme = saved();
    if (theme) {
        root.dataset.theme = theme;
    }

    document.addEventListener('DOMContentLoaded', function () {
        var button = document.querySelector('.theme-toggle');
        if (!button) {
            return;
        }

        function show() {
            // Pressed: dark colours are on
            button.setAttribute('aria-pressed', current() === 'dark' ? 'true' : 'false');
        }

        button.addEventListener('click', function () {
            var next = current() === 'dark' ? 'light' : 'dark';
            root.dataset.theme = next;
            try {
                localStorage.setItem(KEY, next);
            } catch (error) {
                // Not kept: this page still switches
            }
            show();
        });

        // Without a choice, the page follows the system as it changes
        systemDark.addEventListener('change', show);

        show();
        button.hidden = false;
    });
})();
