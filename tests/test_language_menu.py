"""
The language menu in the header: a flag per language. A choice posts to Django's
set_language view, which keeps it in a cookie that SiteLanguageMiddleware reads.
"""

import re

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.urls import reverse

COOKIE = settings.LANGUAGE_COOKIE_NAME


def menu_of(response):
    html = response.content.decode()
    return re.search(r'<details class="menu language-menu">.*?</details>', html, re.S).group(0)


def choose(client, language, next_url='/'):
    return client.post(reverse('set_language'), {'language': language, 'next': next_url})


@pytest.mark.django_db
def test_menu_offers_every_language_with_its_flag(client):
    menu = menu_of(client.get(reverse('home')))

    for code, name in [('en', 'English'), ('sv', 'Svenska')]:
        assert re.search(
            rf'<button class="button language-menu__choice" type="submit" name="language" value="{code}"'
            rf'[^>]*>\s*<img class="flag" src="/static/flags/{code}.svg"[^>]*>{name}\s*</button>',
            menu,
        ), code


@pytest.mark.parametrize('code, _name', settings.LANGUAGES)
def test_every_language_has_a_flag_file(code, _name):
    assert finders.find(f'flags/{code}.svg')


@pytest.mark.django_db
def test_menu_shows_the_flag_of_the_current_language(client):
    english = menu_of(client.get(reverse('home')))
    client.cookies[COOKIE] = 'sv'
    swedish = menu_of(client.get(reverse('home')))

    assert '<summary aria-label="Language" title="Language">' in english
    assert re.search(r'<summary[^>]*>\s*<img class="flag" src="/static/flags/en.svg"', english)
    assert 'value="en" lang="en" aria-current="true"' in english
    assert '<summary aria-label="Språk" title="Språk">' in swedish
    assert re.search(r'<summary[^>]*>\s*<img class="flag" src="/static/flags/sv.svg"', swedish)
    assert 'value="sv" lang="sv" aria-current="true"' in swedish


@pytest.mark.django_db
def test_menu_is_there_for_members_too(client, django_user_model):
    client.force_login(
        django_user_model.objects.create_user(username='m', email='m@example.com', password='pass12345')
    )

    assert 'value="sv"' in menu_of(client.get(reverse('home')))


@pytest.mark.django_db
def test_menu_comes_back_to_the_same_page(client):
    menu = menu_of(client.get(reverse('account_login') + '?next=/latest/'))

    assert '<input type="hidden" name="next" value="/accounts/login/?next=/latest/">' in menu


@pytest.mark.django_db
def test_choosing_swedish_sets_the_cookie_and_the_pages_follow(client):
    response = choose(client, 'sv', '/accounts/login/')

    assert response.status_code == 302
    assert response['Location'] == '/accounts/login/'
    cookie = response.cookies[COOKIE]
    assert cookie.value == 'sv'
    assert cookie['max-age'] == 60 * 60 * 24 * 365
    assert cookie['httponly'] is True
    assert cookie['samesite'] == 'Lax'
    page = client.get('/accounts/login/').content.decode()
    assert '<html lang="sv">' in page
    assert '>Logga in</a>' in page


@pytest.mark.django_db
def test_choosing_english_on_a_swedish_site(client, settings):
    settings.LANGUAGE_CODE = 'sv'
    assert '>Logga in</a>' in client.get(reverse('home')).content.decode()

    choose(client, 'en')

    assert '>Sign in</a>' in client.get(reverse('home')).content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize('next_url', ['https://evil.example.com/', '//evil.example.com/x'])
def test_choice_does_not_lead_to_another_site(client, next_url):
    response = choose(client, 'sv', next_url)

    assert response.status_code == 302
    assert response['Location'] == '/'


@pytest.mark.django_db
@pytest.mark.parametrize('language', ['de', 'xx', ''])
def test_a_language_the_site_does_not_have_changes_nothing(client, language):
    choose(client, language)

    assert '<html lang="en">' in client.get(reverse('home')).content.decode()


@pytest.mark.django_db
def test_choice_needs_a_post(client):
    response = client.get(reverse('set_language'), {'language': 'sv'})

    assert COOKIE not in response.cookies


@pytest.mark.django_db
def test_choice_needs_the_csrf_token(django_user_model):
    from django.test import Client

    response = Client(enforce_csrf_checks=True).post(reverse('set_language'), {'language': 'sv'})

    assert response.status_code == 403


def test_language_cookie_is_secure_in_production():
    source = (settings.BASE_DIR + '/project/settings/production.py')
    assert 'LANGUAGE_COOKIE_SECURE = True' in open(source).read()


@pytest.mark.django_db
def test_error_page_renders_with_the_menu_and_no_request():
    from django.template.loader import render_to_string

    html = render_to_string('500.html')

    assert 'language-menu' in html
    assert 'name="next" value=""' in html
