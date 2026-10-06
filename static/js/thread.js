// The thread page: colour the code blocks in posts (highlight.js) and give each a Copy button
(function () {
    // The button's texts, translated, come from the script tag (thread_detail.html)
    var text = document.currentScript.dataset;

    document.querySelectorAll('pre code').forEach(function (block) {
        hljs.highlightElement(block);
    });

    // navigator.clipboard exists only on https and localhost: elsewhere no button
    if (!navigator.clipboard) {
        return;
    }
    document.querySelectorAll('.prose pre').forEach(function (pre) {
        // The button sits in a wrapper, not in the pre, which scrolls sideways
        var wrapper = document.createElement('div');
        wrapper.className = 'code-block';
        pre.replaceWith(wrapper);
        wrapper.append(pre);

        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'code-block__copy';
        button.textContent = text.copy;
        wrapper.append(button);

        var reset;
        function say(message) {
            button.textContent = message;
            clearTimeout(reset);
            reset = setTimeout(function () {
                button.textContent = text.copy;
            }, 2000);
        }

        button.addEventListener('click', function () {
            // textContent: the code as typed, without the highlighting markup
            navigator.clipboard.writeText(pre.textContent.replace(/\n$/, '')).then(function () {
                say(text.copied);
            }, function () {
                say(text.notCopied);
            });
        });
    });
})();
