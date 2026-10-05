"""
Members change their own replies: an Edit link on the thread page leads to the form, and
saving leads back to the reply, which then says when it was edited.
"""

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from forums.models import Post, Posting

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@example.com', 'testpass123')


@pytest.fixture
def client(client, author):
    client.force_login(author)
    return client


@pytest.fixture
def forum(add_forum):
    return add_forum('The house', 'Repairs')


@pytest.fixture
def thread(forum, reader, add_thread):
    return add_thread('Greenhouse', 'Text', forum, reader)


@pytest.fixture
def post(thread, author, add_post):
    return add_post('As first written', thread, author)


def edit_url(post):
    return reverse('post_update', args=[post.thread_id, post.pk])


def thread_page(client, thread):
    return client.get(reverse('thread_detail', args=[thread.pk])).content.decode()


def test_author_sees_the_edit_link(client, thread, post):
    assert edit_url(post) in thread_page(client, thread)


def test_other_members_see_no_edit_link(client, reader, thread, post):
    client.force_login(reader)
    assert edit_url(post) not in thread_page(client, thread)


def test_form_shows_the_saved_text(client, post):
    resp = client.get(edit_url(post))
    assert resp.status_code == 200
    assert 'As first written</textarea>' in resp.content.decode()


def test_author_edits_the_reply_and_it_is_marked(client, thread, post, security_log):
    resp = client.post(edit_url(post), {'text': 'Thought again'})

    assert resp.status_code == 302
    assert resp.url == f'{reverse("thread_detail", args=[thread.pk])}?page=1#post-{post.pk}'
    post.refresh_from_db()
    assert post.text == 'Thought again'
    assert post.edited is not None
    assert 'post__edited' in thread_page(client, thread)
    assert not [line for line in security_log() if line.startswith('moderation')]


def test_saving_leads_back_to_the_replys_page(client, thread, author, add_post, site_settings):
    site_settings(posts_per_page=2)
    posts = [add_post(f'Reply {n}', thread, author) for n in range(5)]

    resp = client.post(edit_url(posts[2]), {'text': 'Changed'})

    assert resp.url == f'{reverse("thread_detail", args=[thread.pk])}?page=2#post-{posts[2].pk}'


def test_empty_text_is_refused(client, post):
    resp = client.post(edit_url(post), {'text': ''})
    assert resp.status_code == 200
    post.refresh_from_db()
    assert post.text == 'As first written'
    assert post.edited is None


@pytest.mark.parametrize('method', ['get', 'post'])
def test_other_members_cannot_edit(client, reader, post, method):
    client.force_login(reader)
    resp = getattr(client, method)(edit_url(post), {'text': 'Not mine'})
    assert resp.status_code == 403
    assert Post.objects.get(pk=post.pk).text == 'As first written'


def test_visitors_are_sent_to_the_login_page(client, post):
    client.logout()
    resp = client.post(edit_url(post), {'text': 'Anyone'})
    assert resp.status_code == 302
    assert resp.url.startswith(reverse('account_login'))
    assert Post.objects.get(pk=post.pk).text == 'As first written'


def test_reply_is_edited_only_under_its_own_thread(client, forum, author, post, add_thread):
    other = add_thread('Another', 'Text', forum, author)
    resp = client.post(reverse('post_update', args=[other.pk, post.pk]), {'text': 'Changed'})
    assert resp.status_code == 404


def test_author_edits_in_a_closed_forum(client, forum, post):
    forum.posting = Posting.MODERATORS_ONLY
    forum.save()
    resp = client.post(edit_url(post), {'text': 'Still mine'})
    assert resp.status_code == 302
    assert Post.objects.get(pk=post.pk).text == 'Still mine'


def test_edits_do_not_count_against_the_posting_limit(client, post, rates):
    rates(posting_burst='1/min')
    for n in range(3):
        assert client.post(edit_url(post), {'text': f'Version {n}'}).status_code == 302


def test_edit_sends_no_notification(client, post, django_capture_on_commit_callbacks, mailoutbox):
    with django_capture_on_commit_callbacks(execute=True):
        client.post(edit_url(post), {'text': 'Thought again'})
    assert mailoutbox == []


def test_change_post_permission_edits_others_replies_and_is_logged(
    client, add_user, add_totp, thread, post, author, security_log
):
    editor = add_user('editor', 'editor@example.com', 'testpass123')
    editor.user_permissions.add(Permission.objects.get(codename='change_post'))
    add_totp(editor)
    client.force_login(editor)

    assert edit_url(post) in thread_page(client, thread)
    resp = client.post(edit_url(post), {'text': 'Tidied up'})

    assert resp.status_code == 302
    assert Post.objects.get(pk=post.pk).text == 'Tidied up'
    assert (
        f'action=change user={editor.pk} object=post id={post.pk} owner={author.pk}'
        in security_log()[-1]
    )
