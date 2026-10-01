import pytest
from django.apps import apps
from django.conf import settings
from django.db import models
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from forums.models import Post, Thread


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@email.com', 'testpass123')


@pytest.fixture
def forum(add_forum):
    return add_forum(title='Testforum', description='A test forum')


@pytest.fixture
def thread(add_thread, forum, author):
    return add_thread(title='Testtitle', text='Thread text', forum=forum, user=author)


@pytest.fixture
def form_urls(forum, thread):
    return {
        'thread_add': reverse('thread_add', args=(forum.id,)),
        'thread_update': reverse('thread_update', args=(thread.id,)),
        'post_add': reverse('post_add', args=(thread.id,)),
    }


# Forms


@pytest.mark.django_db
@pytest.mark.parametrize('page', ['thread_add', 'thread_update', 'post_add'])
def test_text_is_edited_in_a_plain_textarea(client, author, form_urls, page):
    client.force_login(author)

    resp = client.get(form_urls[page])

    assertContains(resp, '<textarea name="text"')
    assertContains(resp, 'Markdown')
    for leftover in ('martor', 'semantic', 'plugins/', 'ace.'):
        assertNotContains(resp, leftover)


@pytest.mark.django_db
def test_thread_update_form_shows_the_saved_markdown(client, author, form_urls, thread):
    thread.text = '**bold** & <b>raw</b>'
    thread.save()
    client.force_login(author)

    resp = client.get(form_urls['thread_update'])

    assertContains(resp, '**bold** &amp; &lt;b&gt;raw&lt;/b&gt;')


@pytest.mark.django_db
def test_post_is_saved_as_typed(client, author, form_urls, thread):
    client.force_login(author)
    text = '# Title\n\n```python\nprint("hi")\n```'

    client.post(form_urls['post_add'], {'text': text})

    assert Post.objects.get(thread=thread).text == text


# Thread page


@pytest.mark.django_db
def test_thread_page_highlights_code_with_our_own_script(client, thread):
    resp = client.get(reverse('thread_detail', args=(thread.id,)))

    assertContains(resp, 'js/highlight.min.js')
    assertContains(resp, 'hljs.highlightElement')
    for leftover in ('semantic', 'plugins/'):
        assertNotContains(resp, leftover)


# martor is gone


@pytest.mark.parametrize('model', [Thread, Post])
def test_text_is_a_plain_text_field(model):
    assert type(model._meta.get_field('text')) is models.TextField


def test_martor_is_not_installed():
    assert not apps.is_installed('martor')
    assert not [name for name in dir(settings) if name.startswith(('MARTOR', 'MARKDOWNX'))]


@pytest.mark.django_db
@pytest.mark.parametrize('path', ['/martor/markdownify/', '/martor/uploader/', '/martor/search-user/'])
def test_martor_endpoints_are_gone(client, author, path):
    client.force_login(author)

    assert client.post(path, {'content': '**x**'}).status_code == 404
