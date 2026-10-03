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

    // EasyMDE's own buttons are Font Awesome icons. Ours get the class "icon" instead, and
    // editor.css draws each one from static/icons by the button's name.
    function button(name, action, title, noDisable) {
        return {name: name, action: action, title: title, className: 'icon', noDisable: noDisable};
    }

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
            button('bold', EasyMDE.toggleBold, 'Bold'),
            button('italic', EasyMDE.toggleItalic, 'Italic'),
            button('strikethrough', EasyMDE.toggleStrikethrough, 'Strikethrough'),
            button('heading', EasyMDE.toggleHeadingSmaller, 'Heading'),
            '|',
            button('quote', EasyMDE.toggleBlockquote, 'Quote'),
            button('code', EasyMDE.toggleCodeBlock, 'Code'),
            button('unordered-list', EasyMDE.toggleUnorderedList, 'Bulleted list'),
            button('ordered-list', EasyMDE.toggleOrderedList, 'Numbered list'),
            '|',
            button('link', EasyMDE.drawLink, 'Link'),
            button('table', EasyMDE.drawTable, 'Table'),
            '|',
            button('preview', EasyMDE.togglePreview, 'Preview', true)
        ]
    });

    // The toolbar replaces the Markdown hint under the field; it stays for the plain textarea.
    var hint = document.getElementById(textarea.id + '_helptext');
    if (hint) {
        hint.hidden = true;
    }
})();
