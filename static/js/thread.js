// The thread page: colour the code blocks in posts (highlight.js)
document.querySelectorAll('pre code').forEach(function (block) {
    hljs.highlightElement(block);
});
