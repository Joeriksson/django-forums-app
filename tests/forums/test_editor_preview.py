import pytest
from django.test import Client
from django.urls import reverse

from forums.markdown import render


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@email.com', 'testpass123')


@pytest.fixture
def url():
    return reverse('markdown_preview')


@pytest.mark.django_db
def test_preview_renders_like_a_saved_post(client, author, url):
    client.force_login(author)
    text = '**bold** ~~gone~~ https://example.com\n\n<script>alert(1)</script>'

    resp = client.post(url, {'text': text})

    assert resp.status_code == 200
    html = resp.content.decode()
    assert html == render(text)
    assert '<strong>bold</strong>' in html
    assert '<script' not in html


@pytest.mark.django_db
def test_preview_of_empty_text_is_empty(client, author, url):
    client.force_login(author)

    assert client.post(url, {'text': ''}).content == b''
    assert client.post(url).content == b''


@pytest.mark.django_db
def test_preview_needs_a_login(client, url):
    resp = client.post(url, {'text': '**bold**'})

    assert resp.status_code == 302
    assert resp.url.startswith(reverse('account_login'))


@pytest.mark.django_db
def test_preview_accepts_post_only(client, author, url):
    client.force_login(author)

    assert client.get(url).status_code == 405


@pytest.mark.django_db
def test_preview_needs_a_csrf_token(author, url):
    client = Client(enforce_csrf_checks=True)
    client.force_login(author)

    assert client.post(url, {'text': '**bold**'}).status_code == 403
