import json
import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders

# In production a {% static %} path missing from the manifest makes the page fail with a 500,
# so every path the project templates use must exist.
STATIC_TAG = re.compile(r"""{%\s*static\s+['"]([^'"]+)['"]\s*%}""")
# Commented-out tags are never rendered
COMMENT = re.compile(r'{#.*?#}|{%\s*comment\b.*?%}.*?{%\s*endcomment\s*%}', re.DOTALL)


def template_static_paths():
    for template_dir in settings.TEMPLATES[0]['DIRS']:
        for template in Path(template_dir).rglob('*.html'):
            for path in STATIC_TAG.findall(COMMENT.sub('', template.read_text())):
                yield template.relative_to(template_dir), path


def test_templates_use_static_files():
    assert list(template_static_paths())


def test_static_files_in_templates_exist():
    missing = [
        f'{template}: {path}'
        for template, path in template_static_paths()
        if not finders.find(path)
    ]
    assert missing == []


# Font Awesome's js/all.js carries its own stylesheet and would add it to the page as an
# inline <style>. _base.html switches that off; css/fontawesome-svg.css is a copy of it.
FONTAWESOME_STYLES = re.compile(r'var baseStyles = ("(?:[^"\\]|\\.)*");')


def fontawesome_styles_in_script():
    script = Path(finders.find('js/all.js')).read_text()
    return json.loads(FONTAWESOME_STYLES.search(script).group(1))


def test_fontawesome_stylesheet_matches_the_script():
    stylesheet = Path(finders.find('css/fontawesome-svg.css')).read_text()
    # After the licence comment at the top
    rules = stylesheet.split('*/', 1)[1].strip()

    assert rules == fontawesome_styles_in_script().strip(), (
        'js/all.js was replaced without css/fontawesome-svg.css. Put the text of '
        '`var baseStyles = "..."` from js/all.js (unescaped) into the stylesheet, '
        'below the licence comment.'
    )


def test_fontawesome_script_is_told_not_to_add_styles():
    base = (Path(settings.TEMPLATES[0]['DIRS'][0]) / '_base.html').read_text()

    assert re.search(r'<script[^>]*js/all\.js[^>]*data-auto-add-css="false"', base)
    assert 'css/fontawesome-svg.css' in base
