// The bell in the header: the number of unread notifications is on the page when it
// loads. This asks for it again now and then, so news shows without a reload, on the
// bell and first in the page's title (for a tab in the background).
(function () {
    var INTERVAL = 30000;
    var url = document.currentScript.dataset.url;
    var bell = document.querySelector('.bell');
    if (!bell) {
        return;
    }
    var badge = bell.querySelector('.bell__count');
    var number = bell.querySelector('.bell__number');
    var count = Number(bell.dataset.count);
    // The page's own title, without the number the server put first
    var title = count ? document.title.replace('(' + count + ') ', '') : document.title;
    var timer;

    function show(unread) {
        count = unread;
        bell.dataset.count = unread;
        badge.hidden = !unread;
        number.textContent = unread > 9 ? '9+' : unread;
        document.title = (unread ? '(' + unread + ') ' : '') + title;
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
                if (data && data.unread !== count) {
                    show(data.unread);
                }
            })
            .catch(function () {
                // Offline or a server error: the number stays, the next round tries again
            });
    }

    timer = setInterval(refresh, INTERVAL);
    document.addEventListener('visibilitychange', refresh);
})();
