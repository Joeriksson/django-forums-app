// Turns the "text" textarea of a thread or post form into a Markdown editor (EasyMDE).
(function () {
    var previewUrl = document.currentScript.dataset.previewUrl;
    var textarea = document.querySelector('textarea[name="text"]');
    if (!textarea || typeof EasyMDE === 'undefined') {
        return;
    }
    var csrfToken = textarea.form.querySelector('input[name="csrfmiddlewaretoken"]').value;
    var latestRequest = 0;

    // The preview is rendered by the server, so it shows exactly what the saved text will look like.
    function renderPreview(text, preview) {
        var request = ++latestRequest;
        var body = new URLSearchParams({text: text});
        fetch(previewUrl, {
            method: 'POST',
            headers: {'X-CSRFToken': csrfToken},
            body: body,
            credentials: 'same-origin'
        }).then(function (response) {
            // A redirect means the login has expired
            if (!response.ok || response.redirected) {
                throw new Error('preview failed');
            }
            return response.text();
        }).then(function (html) {
            if (request === latestRequest) {
                preview.innerHTML = html;
            }
        }).catch(function () {
            if (request === latestRequest) {
                preview.textContent = 'The preview could not be loaded.';
            }
        });
        return 'Loading preview…';
    }

    // The editor hides the textarea, and a browser cannot show its "required" message on a
    // hidden field: the form would silently refuse to submit. The server still checks it.
    textarea.required = false;

    new EasyMDE({
        element: textarea,
        forceSync: true,
        autoDownloadFontAwesome: false,
        spellChecker: false,
        nativeSpellcheck: true,
        inputStyle: 'contenteditable',
        status: false,
        previewRender: renderPreview,
        toolbar: [
            'bold', 'italic', 'strikethrough', 'heading', '|',
            'quote', 'code', 'unordered-list', 'ordered-list', '|',
            'link', 'table', '|',
            'preview'
        ]
    });

    // The toolbar replaces the Markdown hint under the field; it stays for the plain textarea.
    var hint = document.getElementById(textarea.id + '_helptext');
    if (hint) {
        hint.hidden = true;
    }
})();
