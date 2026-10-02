"""The broker (Redis) is down: the mail isn't queued, but the request that wanted it still succeeds."""

import logging

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from kombu.exceptions import OperationalError

from forums.models import Forum, Notification, Post, Thread
from forums.tasks import send_notifications_task
from project.utils import queue_task
from users.models import Invitation
from users.tasks import send_invitation_email_task, send_welcome_email_task

User = get_user_model()


def broker_down(*args, **kwargs):
    raise OperationalError('Error 111 connecting to redis:6379. Connection refused.')


def queue_errors(caplog):
    return [r for r in caplog.records if r.name == 'project.utils' and r.levelno == logging.ERROR]


def test_queue_task_logs_a_broker_failure_and_carries_on(monkeypatch, caplog):
    monkeypatch.setattr(send_welcome_email_task, 'delay', broker_down)

    queue_task(send_welcome_email_task, 'anna@example.com')

    (error,) = queue_errors(caplog)
    assert 'send_welcome_email_task' in error.getMessage()
    # The arguments can hold email addresses
    assert 'anna@example.com' not in caplog.text


def test_queue_task_lets_other_errors_through(monkeypatch):
    def broken(*args):
        raise ValueError('a bug in the task')

    monkeypatch.setattr(send_welcome_email_task, 'delay', broken)

    with pytest.raises(ValueError):
        queue_task(send_welcome_email_task, 'anna@example.com')


@pytest.fixture
def thread_with_subscriber(db):
    author = User.objects.create_user(username='author', email='author@example.com', password='x')
    subscriber = User.objects.create_user(username='sub', email='sub@example.com', password='x')
    forum = Forum.objects.create(title='Forum', description='Description')
    thread = Thread.objects.create(title='Thread', text='Text', forum=forum, user=author)
    Notification.objects.create(thread=thread, user=subscriber)
    return thread, author


def test_post_is_created_when_the_notification_cannot_be_queued(
    client, thread_with_subscriber, monkeypatch, caplog, django_capture_on_commit_callbacks
):
    thread, author = thread_with_subscriber
    monkeypatch.setattr(send_notifications_task, 'delay', broker_down)
    client.force_login(author)

    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post(reverse('post_add', kwargs={'pk': thread.pk}), {'text': 'A reply'})

    assert resp.status_code == 302
    assert Post.objects.filter(thread=thread, text='A reply').count() == 1
    assert len(queue_errors(caplog)) == 1


def test_notification_is_queued_only_after_the_commit(
    thread_with_subscriber, notification_calls, django_capture_on_commit_callbacks
):
    thread, author = thread_with_subscriber

    with django_capture_on_commit_callbacks() as callbacks:
        Post.objects.create(text='A reply', thread=thread, user=author)
        assert notification_calls == []

    for callback in callbacks:
        callback()
    assert len(notification_calls) == 1


def test_signup_succeeds_when_the_welcome_mail_cannot_be_queued(
    client, db, monkeypatch, caplog, django_capture_on_commit_callbacks
):
    monkeypatch.setattr(send_welcome_email_task, 'delay', broker_down)

    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post(
            reverse('account_signup'), {'email': 'new@example.com', 'password1': 'a-long-test-pass-123'}
        )

    assert resp.status_code == 302
    assert User.objects.filter(email='new@example.com').exists()
    assert len(queue_errors(caplog)) == 1


def test_invitation_is_saved_when_its_mail_cannot_be_queued(
    client, add_totp, monkeypatch, caplog, django_capture_on_commit_callbacks
):
    boss = User.objects.create_superuser(username='boss', email='boss@example.com')
    add_totp(boss)
    client.force_login(boss)
    monkeypatch.setattr(send_invitation_email_task, 'delay', broker_down)

    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post(reverse('admin:users_invitation_add'), {'email': 'anna@example.com'})

    assert resp.status_code == 302
    invitation = Invitation.objects.get(email='anna@example.com')
    # No "Sent" time: the admin list shows it, and "Resend invitation" sends it later
    assert invitation.sent_at is None
    assert len(queue_errors(caplog)) == 1


def test_notification_task_retries_like_the_other_mail_tasks():
    for task in (send_notifications_task, send_welcome_email_task, send_invitation_email_task):
        assert task.autoretry_for == (Exception,), task.name
        assert task.max_retries == 3, task.name
        assert task.retry_backoff is True, task.name


def test_queuing_gives_up_quickly_and_keeps_no_results():
    from project.celery import app

    # Without these, a request waits about 20 seconds for a refused connection
    # and minutes for a silent one before failing
    assert app.conf.task_ignore_result is True
    assert app.conf.result_backend is None
    assert app.conf.broker_transport_options['socket_connect_timeout'] <= 3
    assert app.conf.task_publish_retry_policy['max_retries'] <= 1
