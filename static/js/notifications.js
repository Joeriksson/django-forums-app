// The bell and the envelope in the header: the numbers of threads with unread replies and
// of conversations with unread messages are on the page when it loads. This asks for them
// again now and then, so news shows without a reload, on each icon and, added together,
// first in the page's title (for a tab in the background).
(function () {
    var INTERVAL = 30000;
    var url = document.currentScript.dataset.url;
    var bell = document.querySelector('.bell');
    if (!bell) {
        return;
    }
    // Each icon under the name of its number in the answer, with the class its badge
    // is named after
    var icons = {
        replies: {link: bell, name: 'bell'},
        messages: {link: document.querySelector('.envelope'), name: 'envelope'},
    };
    var keys = Object.keys(icons);
    var counts = {};
    keys.forEach(function (key) {
        counts[key] = Number(icons[key].link.dataset.count);
    });
    var total = sum(counts);
    // The page's own title, without the number the server put first
    var title = total ? document.title.replace('(' + total + ') ', '') : document.title;
    var timer;

    function sum(numbers) {
        return keys.reduce(function (all, key) {
            return all + numbers[key];
        }, 0);
    }

    function show(data) {
        keys.forEach(function (key) {
            var icon = icons[key];
            var unread = data[key];
            counts[key] = unread;
            icon.link.dataset.count = unread;
            icon.link.querySelector('.' + icon.name + '__count').hidden = !unread;
            icon.link.querySelector('.' + icon.name + '__number').textContent = unread > 9 ? '9+' : unread;
        });
        var all = sum(counts);
        document.title = (all ? '(' + all + ') ' : '') + title;
    }

    function changed(data) {
        return keys.some(function (key) {
            return data[key] !== counts[key];
        });
    }

    function refresh() {
        // A hidden tab doesn't ask; it does as soon as it is looked at again
        if (document.visibilityState !== 'visible') {
            return;
        }
        // Redirects are not followed: one to the login page means the session has ended
        fetch(url, {redirect: 'manual', headers: {Accept: 'application/json'}})
            .then(function (response) {
                if (response.type === 'opaqueredirect' || response.status === 403) {
                    clearInterval(timer);
                    document.removeEventListener('visibilitychange', refresh);
                    return null;
                }
                return response.ok ? response.json() : null;
            })
            .then(function (data) {
                if (data && changed(data)) {
                    show(data);
                }
            })
            .catch(function () {
                // Offline or a server error: the numbers stay, the next round tries again
            });
    }

    timer = setInterval(refresh, INTERVAL);
    document.addEventListener('visibilitychange', refresh);
})();
