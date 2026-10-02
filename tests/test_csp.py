"""Every response carries a Content Security Policy that allows no inline code."""

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from project.middleware import ContentSecurityPolicyMiddleware, build_policy

HEADER = 'Content-Security-Policy'
REPORT_ONLY_HEADER = 'Content-Security-Policy-Report-Only'


def directives(header):
    """{'script-src': ["'self'", ...], ...} from a policy header."""
    return {
        name: sources
        for name, *sources in (part.split() for part in header.split(';') if part.strip())
    }


@pytest.mark.django_db
@pytest.mark.parametrize('url', ['/', '/forums/', '/accounts/login/', '/api/forums/', '/no-such-page/'])
def test_every_response_has_the_policy(client, url):
    resp = client.get(url)

    assert "default-src 'self'" in resp[HEADER]
    assert REPORT_ONLY_HEADER not in resp


@pytest.mark.django_db
def test_policy_allows_no_inline_code_or_eval(client):
    policy = client.get(reverse('home'))[HEADER]

    assert 'unsafe-inline' not in policy
    assert 'unsafe-eval' not in policy
    assert '*' not in policy


@pytest.mark.django_db
def test_policy_directives(client):
    policy = directives(client.get(reverse('home'))[HEADER])

    assert policy['default-src'] == ["'self'"]
    # Our own files, plus the CDNs _base.html loads Bootstrap, jQuery and Popper from
    assert policy['script-src'] == [
        "'self'",
        'https://code.jquery.com',
        'https://cdnjs.cloudflare.com',
        'https://stackpath.bootstrapcdn.com',
    ]
    assert policy['style-src'] == ["'self'", 'https://stackpath.bootstrapcdn.com']
    # data: is the QR code on the two-factor setup page; https: is images in posts
    assert policy['img-src'] == ["'self'", 'data:', 'https:']
    assert policy['object-src'] == ["'none'"]
    assert policy['base-uri'] == ["'self'"]
    assert policy['frame-ancestors'] == ["'none'"]
    # The GitHub login form posts to this site, which redirects to GitHub
    assert policy['form-action'] == ["'self'", 'https://github.com']


def test_every_script_host_in_the_base_template_is_allowed(settings):
    import re
    from pathlib import Path

    base = (Path(settings.TEMPLATES[0]['DIRS'][0]) / '_base.html').read_text()
    hosts = set(re.findall(r'(?:src|href)="(https://[^/"]+)/', base))

    allowed = set(settings.SECURE_CSP['script-src']) | set(settings.SECURE_CSP['style-src'])
    assert hosts and hosts <= allowed


def test_build_policy():
    policy = {'default-src': ["'self'"], 'img-src': ["'self'", 'data:']}

    assert build_policy(policy) == "default-src 'self'; img-src 'self' data:"
    assert build_policy({}) == ''


def get_response_with(settings, **config):
    for name, value in config.items():
        setattr(settings, name, value)
    middleware = ContentSecurityPolicyMiddleware(lambda request: HttpResponse('ok'))
    return middleware(RequestFactory().get('/'))


def test_report_only_policy_goes_into_the_report_only_header(settings):
    resp = get_response_with(
        settings, SECURE_CSP={}, SECURE_CSP_REPORT_ONLY={'default-src': ["'self'"]}
    )

    assert HEADER not in resp
    assert resp[REPORT_ONLY_HEADER] == "default-src 'self'"


def test_a_view_can_set_its_own_policy(settings):
    def view(request):
        response = HttpResponse('ok')
        response[HEADER] = "default-src 'none'"
        return response

    settings.SECURE_CSP = {'default-src': ["'self'"]}
    resp = ContentSecurityPolicyMiddleware(view)(RequestFactory().get('/'))

    assert resp[HEADER] == "default-src 'none'"


@pytest.mark.parametrize('env, enforced', [(None, True), ('false', True), ('true', False)])
def test_report_only_switch(monkeypatch, env, enforced):
    import importlib
    import sys

    monkeypatch.delenv('DJANGO_CSP_REPORT_ONLY', raising=False)
    if env is not None:
        monkeypatch.setenv('DJANGO_CSP_REPORT_ONLY', env)
    original = sys.modules.pop('project.settings.base')
    try:
        base = importlib.import_module('project.settings.base')
    finally:
        sys.modules['project.settings.base'] = original

    assert bool(base.SECURE_CSP) is enforced
    assert bool(base.SECURE_CSP_REPORT_ONLY) is not enforced
