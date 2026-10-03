"""
The project templates use the site's own class names (static/css/base.css), not
Bootstrap's: Bootstrap is gone, and nothing styles its names any more.
"""

import re
from pathlib import Path

from django.conf import settings

# Never rendered, so they may say anything
COMMENT = re.compile(r'{#.*?#}|{%\s*comment\b.*?%}.*?{%\s*endcomment\s*%}|<!--.*?-->', re.DOTALL)
CLASS_ATTR = re.compile(r'\sclass="([^"]*)"')
BUTTON = re.compile(r'<button\b[^>]*>', re.IGNORECASE)

BOOTSTRAP_CLASSES = re.compile(
    r'^(btn(-.+)?|card(-.+)?|form-group|form-control|jumbotron|float-(left|right)'
    r'|list-group(-.+)?|text-muted|container(-fluid)?|navbar(-.+)?|alert(-.+)?)$'
)


def project_templates():
    for template_dir in settings.TEMPLATES[0]['DIRS']:
        for template in sorted(Path(template_dir).rglob('*.html')):
            yield template.relative_to(template_dir), COMMENT.sub('', template.read_text())


def test_templates_use_no_bootstrap_class_names():
    found = [
        f'{name}: {cls}'
        for name, text in project_templates()
        for attr in CLASS_ATTR.findall(text)
        for cls in attr.split()
        if BOOTSTRAP_CLASSES.match(cls)
    ]

    assert found == []


def test_every_button_has_the_button_class():
    # Bare <button>s are not styled: the editor's toolbar has its own
    found = [
        f'{name}: {tag}'
        for name, text in project_templates()
        for tag in BUTTON.findall(text)
        if 'button' not in (CLASS_ATTR.search(tag) or [None, ''])[1].split()
    ]

    assert found == []
