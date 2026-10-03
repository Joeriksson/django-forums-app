"""The forum's forms are drawn by Django ({{ form }}), not by crispy-forms."""

from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

FORUM_TEMPLATES = Path(settings.BASE_DIR) / 'templates' / 'forums'


def test_forum_templates_do_not_use_crispy_forms():
    found = [t.name for t in FORUM_TEMPLATES.glob('*.html') if 'crispy' in t.read_text()]

    assert found == []


@pytest.fixture
def poster(add_user):
    return add_user('poster', 'poster@email.com', 'testpass123')


@pytest.fixture
def forum(add_forum):
    return add_forum('General', 'Anything')


@pytest.mark.django_db
def test_form_with_errors_marks_the_field(client, poster, forum):
    client.force_login(poster)

    resp = client.post(reverse('thread_add', args=(forum.id,)), {'title': '', 'text': 'Hi'})

    assert resp.status_code == 200
    content = resp.content.decode()
    assert '<ul class="errorlist" id="id_title_error">' in content
    assert 'aria-invalid="true"' in content
    # The text typed so far comes back
    assert '>\nHi</textarea>' in content


@pytest.mark.django_db
def test_posting_limit_shows_as_an_error_of_the_whole_form(client, poster, forum, rates):
    rates(posting_burst='1/min')
    client.force_login(poster)
    url = reverse('thread_add', args=(forum.id,))
    client.post(url, {'title': 'First', 'text': 'Hi'})

    resp = client.post(url, {'title': 'Second', 'text': 'Hi again'})

    assert resp.status_code == 429
    assert '<ul class="errorlist nonfield">' in resp.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize('has_name', [True, False])
def test_profile_page_says_how_others_see_you(client, poster, has_name):
    if has_name:
        poster.profile.first_name = 'Anna'
        poster.profile.save()
    client.force_login(poster)

    content = client.get(reverse('user_profile_edit', args=(poster.profile.id,))).content.decode()

    assert ('you are shown as Member' in content) is not has_name


@pytest.mark.django_db
@pytest.mark.parametrize('page', ['post_delete', 'thread_delete'])
def test_delete_pages_show_the_display_name_not_the_username(
    client, add_user, add_thread, add_post, forum, page
):
    author = add_user('anna.berg', 'anna@email.com', 'testpass123')
    thread = add_thread('Pelicans', 'Birds', forum, author)
    post = add_post('I saw one', thread, author)
    client.force_login(author)
    args = (thread.id, post.id) if page == 'post_delete' else (forum.id, thread.id)

    content = client.get(reverse(page, args=args)).content.decode()

    assert author.display_name in content
    assert 'anna.berg' not in content
