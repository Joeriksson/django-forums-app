"""
Site settings: one record, edited in the admin, that names the site and holds the
visitors' texts. Pages, emails and authenticator apps take the name from it.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import mail
from django.urls import reverse
from django.views.defaults import server_error
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

from forums.models import Forum, Post, Thread
from pages.models import SiteSettings
from users.adapters import MFAAdapter
from users.models import Invitation
from users.tasks import send_invitation_email_task, send_welcome_email_task

User = get_user_model()

TITLE = 'Lakeside'


@pytest.fixture
def renamed(db):
    site_settings = SiteSettings.load()
    site_settings.title = TITLE
    site_settings.tagline = 'Neighbours talking.'
    site_settings.invitation_note = 'Ask a neighbour for an invitation.'
    site_settings.save()
    return site_settings


@pytest.fixture
def staff_client(client, add_totp):
    boss = User.objects.create_superuser(username='boss', email='boss@example.com')
    add_totp(boss)
    client.force_login(boss)
    return client


# The record


@pytest.mark.django_db
def test_the_migration_creates_the_record_with_todays_texts():
    site_settings = SiteSettings.objects.get()

    assert site_settings.title == 'Wildvasa'
    assert site_settings.tagline == 'A private forum. Sign in to read and write.'
    assert site_settings.invitation_note.startswith('Membership is by invitation.')


@pytest.mark.django_db
def test_load_falls_back_to_the_defaults_without_a_record():
    SiteSettings.objects.all().delete()

    assert SiteSettings.load().title == 'Wildvasa'


@pytest.mark.django_db
def test_there_is_only_ever_one_record():
    SiteSettings(title='Second').save()

    assert SiteSettings.objects.get().title == 'Second'


def test_saving_copies_the_title_to_the_sites_display_name(renamed, settings):
    assert Site.objects.get(pk=settings.SITE_ID).name == TITLE


# Pages


def test_header_and_tab_show_the_title(client, renamed):
    resp = client.get(reverse('account_login'))

    assertContains(resp, f'<a class="site-name" href="{reverse("home")}">{TITLE}</a>')
    assertNotContains(resp, 'Wildvasa')


def test_visitors_home_shows_title_tagline_and_note(client, renamed, settings):
    settings.SIGNUP_OPEN = False

    resp = client.get(reverse('home'))

    assertContains(resp, f'<title>{TITLE}</title>')
    assertContains(resp, f'<h1 class="door__name">{TITLE}</h1>')
    assertContains(resp, 'Neighbours talking.')
    assertContains(resp, 'Ask a neighbour for an invitation.')


def test_texts_are_escaped(client, db, settings):
    settings.SIGNUP_OPEN = False
    site_settings = SiteSettings.load()
    site_settings.tagline = '<b>bold</b>'
    site_settings.save()

    assertContains(client.get(reverse('home')), '&lt;b&gt;bold&lt;/b&gt;')


@pytest.mark.django_db
def test_server_error_page_names_the_site_without_the_database(rf):
    # Django renders 500.html without a request, so without the context processor
    assert b'Wildvasa' in server_error(rf.get('/')).content


# Emails and authenticator apps


def test_allauth_emails_use_the_title(client, renamed, verify_email):
    verify_email(User.objects.create_user(username='m', email='m@example.com', password='x'))
    mail.outbox.clear()

    client.post(reverse('account_reset_password'), {'email': 'm@example.com'})

    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject.startswith(f'[{TITLE}] ')
    assert TITLE in mail.outbox[0].body


def test_allauth_emails_ignore_a_stale_sites_name(client, renamed, verify_email):
    # Another process may still hold the old name in Django's Sites cache
    verify_email(User.objects.create_user(username='m', email='m@example.com', password='x'))
    Site.objects.filter(pk=1).update(name='Old name')
    mail.outbox.clear()

    client.post(reverse('account_reset_password'), {'email': 'm@example.com'})

    assert 'Old name' not in mail.outbox[0].subject
    assert 'Old name' not in mail.outbox[0].body


def test_invitation_email_uses_the_title(renamed):
    invitation = Invitation.objects.create(email='new@example.com')
    mail.outbox.clear()

    send_invitation_email_task(invitation.pk)

    assert TITLE in mail.outbox[0].subject
    assert TITLE in mail.outbox[0].body
    assert 'Wildvasa' not in mail.outbox[0].body


def test_welcome_email_uses_the_title(renamed):
    send_welcome_email_task('new@example.com')

    assert TITLE in mail.outbox[0].subject
    assert TITLE in mail.outbox[0].body


def test_authenticator_apps_show_the_title(renamed, settings):
    assert MFAAdapter().get_totp_issuer() == TITLE


# The admin


def test_admin_list_opens_the_record(staff_client):
    site_settings = SiteSettings.load()

    resp = staff_client.get(reverse('admin:pages_sitesettings_changelist'))

    assertRedirects(resp, reverse('admin:pages_sitesettings_change', args=[site_settings.pk]))


def test_admin_edits_the_record(staff_client, settings):
    site_settings = SiteSettings.load()

    staff_client.post(
        reverse('admin:pages_sitesettings_change', args=[site_settings.pk]),
        {
            'title': TITLE, 'tagline': 'T', 'invitation_note': 'N',
            'recent_threads': 3, 'latest_threads': 15, 'threads_per_page': 20, 'posts_per_page': 25,
            'notification_mail_delay': 5,
        },
    )

    assert SiteSettings.load().title == TITLE
    assert Site.objects.get(pk=settings.SITE_ID).name == TITLE


def test_admin_cannot_add_or_delete(staff_client):
    site_settings = SiteSettings.load()

    assert staff_client.get(reverse('admin:pages_sitesettings_add')).status_code == 403
    delete_url = reverse('admin:pages_sitesettings_delete', args=[site_settings.pk])
    assert staff_client.get(delete_url).status_code == 403


# The numbers for lists and pages


@pytest.fixture
def member_client(client, db):
    member = User.objects.create_user(username='member', email='member@example.com', password='x')
    client.force_login(member)
    client.member = member
    return client


@pytest.fixture
def forum(db):
    return Forum.objects.create(title='Trips', description='Where to next')


def add_threads(forum, user, count):
    return [
        Thread.objects.create(title=f'Thread {number}', text='Text', forum=forum, user=user)
        for number in range(count)
    ]


@pytest.mark.django_db
def test_the_migration_starts_the_numbers_at_todays_values():
    site_settings = SiteSettings.objects.get()

    assert site_settings.recent_threads == 3
    assert site_settings.latest_threads == 15
    assert site_settings.threads_per_page == 20
    assert site_settings.posts_per_page == 25


def test_recent_activity_shows_the_set_number(member_client, forum, site_settings):
    site_settings(recent_threads=5)
    add_threads(forum, member_client.member, 6)

    assert len(member_client.get(reverse('home')).context['recent_threads']) == 5


def test_latest_shows_the_set_number(member_client, forum, site_settings):
    site_settings(latest_threads=5)
    add_threads(forum, member_client.member, 6)

    assert len(member_client.get(reverse('latest')).context['threads']) == 5


def test_forum_page_shows_the_set_number_of_threads(member_client, forum, site_settings):
    site_settings(threads_per_page=5)
    add_threads(forum, member_client.member, 6)

    page = member_client.get(reverse('forum_detail', args=[forum.pk])).context['threads']

    assert len(page) == 5
    assert page.paginator.num_pages == 2


def test_thread_page_shows_the_set_number_of_posts(member_client, forum, site_settings):
    site_settings(posts_per_page=5)
    thread = add_threads(forum, member_client.member, 1)[0]
    for number in range(6):
        Post.objects.create(text=f'Reply {number}', thread=thread, user=member_client.member)

    page = member_client.get(reverse('thread_detail', args=[thread.pk])).context['posts']

    assert len(page) == 5
    assert page.paginator.num_pages == 2


@pytest.mark.parametrize(
    'field, low, high',
    [
        ('recent_threads', 0, 11),
        ('latest_threads', 4, 51),
        ('threads_per_page', 4, 101),
        ('posts_per_page', 4, 101),
        ('notification_mail_delay', -1, 31),
    ],
)
def test_admin_refuses_numbers_out_of_range(staff_client, field, low, high):
    url = reverse('admin:pages_sitesettings_change', args=[SiteSettings.PK])
    data = {
        'title': 'T', 'tagline': 'T', 'invitation_note': 'N',
        'recent_threads': 3, 'latest_threads': 15, 'threads_per_page': 20, 'posts_per_page': 25,
        'notification_mail_delay': 5,
    }

    for value in (low, high):
        resp = staff_client.post(url, {**data, field: value})
        assert resp.status_code == 200  # the form again, with the error
        assert getattr(SiteSettings.load(), field) == data[field]
