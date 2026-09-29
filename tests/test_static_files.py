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
