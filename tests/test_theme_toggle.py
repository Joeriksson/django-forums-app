"""
The light/dark switch in the header. The tests don't run a browser: they check the
markup, the script's place and that the palettes follow the page's colour scheme.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.views.defaults import server_error
from pytest_django.asserts import assertContains

CSS = Path(settings.BASE_DIR) / 'static' / 'css'


@pytest.fixture
def page(client, db):
    return client.get(reverse('account_login')).content.decode()


def test_header_has_the_switch_hidden_until_the_script_shows_it(page):
    # Without JavaScript it couldn't work, so it stays hidden
    assert re.search(
        r'<button class="button button--quiet theme-toggle" type="button" '
        r'aria-label="Dark colours" aria-pressed="false" hidden>',
        page,
    )


def test_theme_script_runs_in_the_head_before_the_page_draws(page):
    head = page.split('</head>', 1)[0]
    script = re.search(r'<script src="[^"]*js/theme\.js"></script>', head)
    assert script, 'theme.js must load in <head>'
    # Not deferred: it sets the saved colours before the first paint
    assert 'defer' not in script.group(0)
    assert head.index('js/theme.js') < head.index('css/base.css')


@pytest.mark.django_db
def test_error_page_has_the_switch_too(rf):
    assert b'theme-toggle' in server_error(rf.get('/')).content


@pytest.mark.parametrize('name', ['base.css', 'thread.css'])
def test_palettes_follow_the_colour_scheme_not_the_system_setting(name):
    # light-dark() picks by the page's color-scheme, which the switch can set;
    # a prefers-color-scheme block would ignore the switch
    css = (CSS / name).read_text()
    assert 'prefers-color-scheme' not in css
    assert 'light-dark(' in css


def test_switch_sets_the_colour_scheme():
    css = (CSS / 'base.css').read_text()
    assert re.search(r":root\[data-theme='light'\]\s*\{\s*color-scheme: light;", css)
    assert re.search(r":root\[data-theme='dark'\]\s*\{\s*color-scheme: dark;", css)


def test_switch_icons_exist():
    icons = Path(settings.BASE_DIR) / 'static' / 'icons'
    assert (icons / 'sun.svg').is_file()
    assert (icons / 'moon.svg').is_file()


def test_visitors_see_the_switch_too(client, db):
    assertContains(client.get(reverse('home')), 'theme-toggle')
