// The user menu in the header is a <details>: it opens and closes by itself.
// This only closes it when the visitor clicks elsewhere or presses Escape.
(function () {
    var menus = document.querySelectorAll('details.menu');

    document.addEventListener('click', function (event) {
        menus.forEach(function (menu) {
            if (menu.open && !menu.contains(event.target)) {
                menu.open = false;
            }
        });
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') {
            return;
        }
        menus.forEach(function (menu) {
            if (menu.open) {
                menu.open = false;
                menu.querySelector('summary').focus();
            }
        });
    });
})();
