// The member search for a new message (conversations/member_list.html): shows who fits
// while the name is typed, by fetching the page itself and taking its list. Without
// this script the Search button does the same.
(function () {
    // Characters before a search runs by itself, and how long the typing must pause
    var MIN_LENGTH = 3;
    var WAIT = 300;
    var field = document.querySelector('.search-form input[name="q"]');
    var results = document.getElementById('member-results');
    if (!field || !results || !window.fetch || !window.DOMParser) {
        return;
    }
    var timer;
    var latestRequest = 0;

    function search(words) {
        var request = ++latestRequest;
        var url = new URL(window.location.href);
        url.search = '';
        if (words) {
            url.searchParams.set('q', words);
        }
        fetch(url, {credentials: 'same-origin'})
            .then(function (response) {
                // A redirect means the login has expired: the button will show that
                if (response.redirected) {
                    throw new Error('not logged in');
                }
                // Also when refused for searching too fast: the page says so
                return response.text();
            })
            .then(function (html) {
                var list = new DOMParser().parseFromString(html, 'text/html').getElementById('member-results');
                // Only the answer to what was typed last
                if (list && request === latestRequest) {
                    results.innerHTML = list.innerHTML;
                    // A reload, or coming back from a conversation, keeps the search
                    window.history.replaceState(null, '', url);
                }
            })
            .catch(function () {
                // Offline or a server error: the list stays as it is
            });
    }

    field.addEventListener('input', function () {
        var words = field.value.trim();
        clearTimeout(timer);
        // An emptied field brings back the members already written with
        if (words.length >= MIN_LENGTH || !words) {
            timer = setTimeout(function () {
                search(words);
            }, WAIT);
        }
    });
})();
